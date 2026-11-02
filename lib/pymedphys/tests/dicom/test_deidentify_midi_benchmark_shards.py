# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests of a MIDI benchmark run in shards, and of their combining (D-018).

Every answer key here is made by hand, and every DICOM file is synthetic.
"""

import dataclasses
import json

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_command, text_detection
from pymedphys._dicom.deidentify.midi_benchmark_flips import (
    CHECK_OUTCOMES,
    FlipCheckError,
    flip_check,
    read_check_outcomes,
)
from pymedphys._dicom.deidentify.midi_answer_key import read_answer_key
from pymedphys._dicom.deidentify.midi_benchmark_shards import (
    COUNTS,
    Shard,
    ShardError,
    assign,
    combine,
)

from .test_deidentify_midi_benchmark import _benchmark_key, _source

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)


@pytest.mark.parametrize("text", ["0/2", "3/2", "2", "2/", "/2", "a/b", "02/3", " 1/2"])
def test_a_shard_is_written_as_number_over_count(text):
    with pytest.raises(ShardError, match="number"):
        Shard.parse(text)


def test_a_shard_reads_back_as_written():
    assert str(Shard.parse("6/8")) == "6/8"
    assert Shard.parse("1/1") == Shard(1, 1)


def test_each_patients_inputs_go_to_one_shard_the_heaviest_first():
    shards = assign(["A", "B", "C", "A", "D"], [1, 10, 6, 1, 3], 3)

    # B to shard 1, C to 2, D to 3, then A, the lightest, to 3.
    assert shards == (3, 1, 2, 3, 3)


def test_inputs_without_a_patient_and_without_weight_load_the_first_shard():
    # The patientless input weighs on shard 1, so A goes to shard 2; an
    # input of no pixels counts as one.
    assert assign([None, "A", "B"], [5, 0, 0], 2) == (1, 2, 2)


def test_one_shard_takes_every_input():
    assert assign(["A", None, "B"], [3, 2, 1], 1) == (1, 1, 1)


@pytest.mark.parametrize(
    "shape, expected",
    [
        # The shorter side scaled up to 736, the longer to match.
        ((128, 128), (736, 736)),
        ((128, 256), (736, 1472)),
        # The longer side capped at 2,560, the shorter to match.
        ((3000, 4000), (1920, 2560)),
        # Between, each side rounded to a multiple of 32.
        ((1000, 1010), (992, 1024)),
    ],
)
def test_the_network_reads_a_frame_at_its_input_shape(shape, expected):
    assert benchmark._network_shape(*shape) == expected  # pylint: disable = protected-access


@pytest.mark.parametrize(
    "shape", [(64, 64), (128, 256), (512, 512), (1000, 1010), (3000, 4000), (5000, 40)]
)
def test_the_weight_reads_a_frame_as_the_detector_does(shape):
    # Main's text detector names the shape of its input; this branch's
    # harness repeats it, so the two must agree once main is merged in.
    network_shape = getattr(text_detection, "network_shape", None)
    if not callable(network_shape):
        pytest.skip("this text detector does not name its input's shape")
    # Pylint infers getattr's default alone.
    expected = network_shape(shape, text_detection.DetectionParameters())  # pylint: disable = not-callable

    assert benchmark._network_shape(*shape) == expected  # pylint: disable = protected-access


def _dataset(**elements):
    dataset = pydicom.Dataset()
    for keyword, value in elements.items():
        setattr(dataset, keyword, value)
    return dataset


@pytest.mark.parametrize(
    "elements, expected",
    [
        # The network's input and a tenth of the stored pixels, per frame.
        ({"Rows": 128, "Columns": 128}, 736 * 736 + 128 * 128 // 10),
        (
            {"Rows": 128, "Columns": 128, "NumberOfFrames": "3"},
            3 * (736 * 736 + 128 * 128 // 10),
        ),
        ({"Rows": 3000, "Columns": 4000}, 1920 * 2560 + 1_200_000),
        # A number of frames of none counts as one.
        (
            {"Rows": 128, "Columns": 128, "NumberOfFrames": "0"},
            736 * 736 + 128 * 128 // 10,
        ),
        # No image.
        ({}, 0),
        ({"Rows": 0, "Columns": 128}, 0),
    ],
)
def test_an_instance_weighs_the_text_detectors_work(elements, expected):
    assert benchmark._pixel_weight(_dataset(**elements)) == expected  # pylint: disable = protected-access


def test_the_count_fields_are_the_benchmarks_counts():
    fields = {field.name for field in dataclasses.fields(benchmark.CategoryCounts)}

    assert fields <= COUNTS


def _shard_document(number, count, **fields):
    return {
        "format": benchmark.FORMAT,
        "versions": {"pymedphys": "1", "shard": f"{number}/{count}"},
        **fields,
    }


def test_combining_adds_counts_and_merges_rows_by_their_other_fields():
    first = _shard_document(
        1,
        2,
        headline={"checks": 3, "passed": 2},
        coverage={
            "by_modality": {"CT": {"released": 1}},
            "withheld_places": [
                {"code": "x", "source": "a", "found_in": "", "vr": "LO", "instances": 1}
            ],
        },
        findings=[{"category": "c", "action": "a", "attribute": None, "checks": 2}],
    )
    second = _shard_document(
        2,
        2,
        headline={"checks": 4, "passed": 1},
        coverage={
            "by_modality": {"MR": {"released": 2}, "CT": {"released": 1}},
            "withheld_places": [
                {
                    "code": "y",
                    "source": "b",
                    "found_in": "",
                    "vr": "LO",
                    "instances": 2,
                },
                {
                    "code": "x",
                    "source": "a",
                    "found_in": "",
                    "vr": "LO",
                    "instances": 2,
                },
            ],
        },
        findings=[
            {"category": "c", "action": "a", "attribute": "(0008,0060)", "checks": 1},
            {"category": "c", "action": "a", "attribute": None, "checks": 1},
        ],
    )

    combined = combine([second, first])

    assert combined["versions"] == {"pymedphys": "1", "shard": "combined 2"}
    assert combined["headline"] == {"checks": 7, "passed": 3}
    # The modalities, held unlike, in order; the places, the most first.
    assert list(combined["coverage"]["by_modality"]) == ["CT", "MR"]
    assert combined["coverage"]["by_modality"]["CT"] == {"released": 2}
    assert [row["instances"] for row in combined["coverage"]["withheld_places"]] == [
        3,
        2,
    ]
    assert combined["findings"] == [
        {"category": "c", "action": "a", "attribute": None, "checks": 3},
        {"category": "c", "action": "a", "attribute": "(0008,0060)", "checks": 1},
    ]


def test_categories_are_ordered_with_no_category_last():
    rows = [
        {"family": None, "code": None, "passed": 1},
        {"family": "tcia", "code": "B", "passed": 1},
    ]
    other = [{"family": "hipaa", "code": "A", "passed": 1}]

    combined = combine(
        [
            _shard_document(1, 2, categories=rows),
            _shard_document(2, 2, categories=other),
        ]
    )

    assert [row["family"] for row in combined["categories"]] == [
        "hipaa",
        "tcia",
        None,
    ]


@pytest.mark.parametrize(
    "documents, message",
    [
        ([], "no shards"),
        ([_shard_document(1, 2)], "each shard"),
        ([_shard_document(1, 2), _shard_document(1, 2)], "each shard"),
        ([_shard_document(1, 1), _shard_document(1, 2)], "each shard"),
        (
            [
                _shard_document(1, 2),
                {**_shard_document(2, 2), "format": "other/1"},
            ],
            "formats",
        ),
        (
            [
                _shard_document(1, 2),
                {
                    **_shard_document(2, 2),
                    "versions": {"pymedphys": "2", "shard": "2/2"},
                },
            ],
            "versions",
        ),
        (
            [
                _shard_document(1, 2, headline={"checks": 1}),
                _shard_document(2, 2),
            ],
            "fields",
        ),
        (
            [
                _shard_document(1, 2, note="a"),
                _shard_document(2, 2, note="b"),
            ],
            "cannot be added up",
        ),
        (
            [
                {
                    **_shard_document(1, 2),
                    "versions": {"pymedphys": "1", "shard": None},
                },
                _shard_document(2, 2),
            ],
            "number",
        ),
    ],
)
def test_results_that_are_not_every_shard_of_one_run_are_refused(documents, message):
    with pytest.raises(ShardError, match=message):
        combine(documents)


def _run(tmp_path, name, shard=None):
    return benchmark.run_benchmark(
        tmp_path / "source",
        tmp_path / "key.db",
        tmp_path / name,
        shard=shard,
    )


@pytest.mark.parametrize("count", [2, 3])
def test_the_shards_of_a_run_add_up_to_the_whole_run(tmp_path, count):
    # Two patients, and an answer-key instance that the input does not hold;
    # with three shards, one shard has no input at all.
    _source(tmp_path)
    _benchmark_key(tmp_path)
    whole = _run(tmp_path, "whole").document

    shards = [
        _run(tmp_path, f"shard-{number}", Shard(number, count)).document
        for number in range(1, count + 1)
    ]

    assert whole["versions"]["shard"] is None
    assert [shard["versions"]["shard"] for shard in shards] == [
        f"{number}/{count}" for number in range(1, count + 1)
    ]
    assert all(
        shard["headline"]["checks"] < whole["headline"]["checks"] for shard in shards
    )
    combined = combine(shards)
    assert combined["versions"] == {**whole["versions"], "shard": f"combined {count}"}
    assert {name: value for name, value in combined.items() if name != "versions"} == {
        name: value for name, value in whole.items() if name != "versions"
    }


def test_a_shard_scores_only_its_patients_and_writes_the_others_checks_apart(
    tmp_path,
):
    source = _source(tmp_path)
    key = _benchmark_key(tmp_path)
    patients = {
        path.name: str(pydicom.dcmread(path, stop_before_pixels=True).PatientID)
        for path in source.iterdir()
    }
    assert len(set(patients.values())) == 2

    results = [_run(tmp_path, f"shard-{number}", Shard(number, 2)) for number in (1, 2)]

    total = sum(
        len(answer.checks) for answer in read_answer_key(key).by_sop_instance().values()
    )
    for number, result in enumerate(results, start=1):
        outcomes = read_check_outcomes(tmp_path / f"shard-{number}" / CHECK_OUTCOMES)
        assert len(outcomes.codes) == total
        scored = total - outcomes.codes.count(b"S")
        assert scored == result.document["headline"]["checks"] > 0
    # Each check is scored in exactly one shard.
    first, second = (
        read_check_outcomes(tmp_path / f"shard-{number}" / CHECK_OUTCOMES).codes
        for number in (1, 2)
    )
    assert all((a == ord("S")) != (b == ord("S")) for a, b in zip(first, second))


def test_a_shards_check_outcomes_cannot_be_flip_checked(tmp_path):
    _source(tmp_path)
    key = _benchmark_key(tmp_path)
    _run(tmp_path, "whole")
    _run(tmp_path, "shard", Shard(1, 2))
    whole = read_check_outcomes(tmp_path / "whole" / CHECK_OUTCOMES)
    shard = read_check_outcomes(tmp_path / "shard" / CHECK_OUTCOMES)

    with pytest.raises(FlipCheckError, match="shard"):
        flip_check(
            read_answer_key(key),
            whole,
            dataclasses.replace(shard, preset=None, options=("retain_uids",)),
            "retain_uids",
        )


def test_the_command_runs_shards_and_combines_them(tmp_path, capsys):
    source = _source(tmp_path)
    key = _benchmark_key(tmp_path)
    for number in (1, 2):
        assert (
            midi_benchmark_command.main(
                [
                    "run",
                    "--source",
                    str(source),
                    "--answer-key",
                    str(key),
                    "--work",
                    str(tmp_path / f"shard-{number}"),
                    "--shard",
                    f"{number}/2",
                ]
            )
            == 0
        )
    capsys.readouterr()

    assert (
        midi_benchmark_command.main(
            [
                "combine",
                str(tmp_path / "shard-2" / benchmark.RESULTS_JSON),
                str(tmp_path / "shard-1" / benchmark.RESULTS_JSON),
                "--out",
                str(tmp_path / "combined"),
            ]
        )
        == 0
    )

    combined = tmp_path / "combined"
    document = json.loads((combined / benchmark.RESULTS_JSON).read_text())
    assert document["versions"]["shard"] == "combined 2"
    markdown = (combined / benchmark.RESULTS_MARKDOWN).read_text()
    assert capsys.readouterr().out == markdown
    assert "combined 2" in markdown


def test_the_command_refuses_a_shard_it_cannot_read(tmp_path, capsys):
    with pytest.raises(SystemExit):
        midi_benchmark_command.main(
            [
                "run",
                "--source",
                "s",
                "--answer-key",
                "k",
                "--work",
                "w",
                "--shard",
                "3/2",
            ]
        )
    assert "from 1 to the count" in capsys.readouterr().err

    (tmp_path / "bad.json").write_text("[]")
    with pytest.raises(SystemExit, match="not a shard's results"):
        midi_benchmark_command.main(
            ["combine", str(tmp_path / "bad.json"), "--out", str(tmp_path / "out")]
        )
    with pytest.raises(SystemExit, match="could not be read"):
        midi_benchmark_command.main(
            ["combine", str(tmp_path / "none.json"), "--out", str(tmp_path / "out")]
        )
    (tmp_path / "out").mkdir()
    with pytest.raises(SystemExit, match="must not exist"):
        midi_benchmark_command.main(
            ["combine", str(tmp_path / "bad.json"), "--out", str(tmp_path / "out")]
        )
