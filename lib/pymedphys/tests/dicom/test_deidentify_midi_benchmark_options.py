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

"""Tests of the MIDI benchmark under a custom option set, and its flip check (D-018).

Every DICOM file and answer key is synthetic, as in
``test_deidentify_midi_benchmark``.
"""

import csv
import json
import sqlite3

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    dicom_validation,
    dicom_validation_command,
    dicom_validators,
)
from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_command, midi_script_results
from pymedphys._dicom.deidentify import midi_benchmark_flips as flips
from pymedphys._dicom.deidentify.midi_answer_key import (
    AnswerInstance,
    AnswerKey,
    parse_check,
    read_answer_key,
)
from pymedphys._dicom.deidentify.policy import (
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    SAFE_PRIVATE,
    PolicyError,
    compose_custom_policy,
    compose_policy,
    compose_preset_without,
)
from pymedphys._dicom.deidentify.safe_private import SafePrivateList
from pymedphys._dicom.deidentify.text_detection import TextDetectionError

from . import _synthetic_references as synthetic
from .corpus_runs.clean_pixel_data import RUN as CLEAN_PIXEL_DATA_RUN
from .test_deidentify_midi_benchmark import _benchmark_key, _source

# An invented TG-263 edition, for a preset with Clean Descriptors.
from .test_deidentify_midi_benchmark_presets import (  # noqa: F401  # pylint: disable = unused-import
    _edition,
)

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

UIDS = "retain_uids"


def _run(tmp_path, name, **policy):
    work = tmp_path / name
    document = benchmark.run_benchmark(
        _source(tmp_path / f"{name}-source"),
        _benchmark_key(tmp_path / f"{name}-source"),
        work,
        **policy,
    ).document
    return work, document


@pytest.fixture(name="sources")
def _sources(tmp_path):
    for name in ("basic", "option"):
        (tmp_path / f"{name}-source").mkdir()
    return tmp_path


def test_a_custom_option_set_is_run_and_recorded(sources):
    work, document = _run(sources, "option", options=[UIDS])

    assert document["format"] == "pymedphys-deid-midi-benchmark/3"
    assert document["versions"]["preset"] is None
    assert document["versions"]["options"] == [UIDS]
    assert "| options | retain_uids |" in (work / "benchmark.md").read_text()
    # Retain UIDs keeps the RT Dose's SOP Instance UID, which the answer key
    # asks to be changed.
    (uid_changed,) = [
        row for row in document["findings"] if row["action"] == "uid_changed"
    ]
    assert uid_changed["attribute"] == "(0008,0018)"


def test_a_preset_records_its_options(sources):
    _, document = _run(sources, "basic")
    assert document["versions"]["preset"] == "basic"
    assert document["versions"]["options"] == []


def test_the_mapping_files_name_the_uids_a_kept_uid_file_holds(sources):
    # Under Retain UIDs, a file is named by its UIDs' keyed replacements but
    # holds its source's UIDs, which the validation script compares.
    work, document = _run(sources, "option", options=[UIDS])

    with open(work / "validation-script" / "uid_mapping.csv", newline="") as file:
        mapped = dict(list(csv.reader(file))[1:])
    assert mapped[synthetic.CT_SERIES] == synthetic.CT_SERIES
    assert mapped[synthetic.STUDY] == synthetic.STUDY
    (consistent,) = [
        row for row in document["categories"] if row["code"] == "DICOM-P15-BASIC-U"
    ]
    assert consistent["passed"] == 1 and consistent["failed"] == 0


@pytest.mark.parametrize("policy", [{}, {"options": [UIDS]}])
def test_the_released_answer_key_takes_each_released_files_rows(sources, policy):
    # The mapping that a run writes, and its release, prepare the answer key
    # for NCI's script, under Retain UIDs as under basic.
    work, document = _run(sources, "option", **policy)
    out = sources / "released.db"

    counts = midi_script_results.write_released_answer_key(
        sources / "option-source" / "key.db",
        work / "release",
        work / "validation-script" / "uid_mapping.csv",
        out,
    )

    released = document["coverage"]["instances"]["released"]
    assert counts["released_instances"] == len(list((work / "release").rglob("*.dcm")))
    assert counts["answer_key_instances"] == released
    connection = sqlite3.connect(out)
    try:
        uids = {
            row[0]
            for row in connection.execute("SELECT SOPInstanceUID FROM answer_data")
        }
    finally:
        connection.close()
    assert len(uids) == released
    assert uids <= {synthetic.CT_SLICES[0], synthetic.DOSE}


@pytest.mark.parametrize("policy", [{}, {"options": [UIDS]}])
def test_the_dicom_comparison_pairs_each_released_file(sources, policy):
    # The mapping that a run writes pairs each released file with its input
    # for the DICOM validators, under Retain UIDs as under basic.
    work, _ = _run(sources, "option", **policy)

    source = sources / "option-source" / "source"
    pairs, unpaired = dicom_validation.pairs_from_uid_mapping(
        source, work / "release", work / "validation-script" / "uid_mapping.csv"
    )

    released = len(list((work / "release").rglob("*.dcm")))
    assert len(pairs) == released > 0
    assert unpaired == len(list(source.glob("*.dcm"))) - released


def test_the_dicom_validation_command_reaches_the_comparison(sources, monkeypatch):
    # Under Retain UIDs, the validators' own pairing used to refuse the run.
    work, _ = _run(sources, "option", options=[UIDS])
    compared = []

    def compare(pairs, toolset, *, unpaired, workers):
        del toolset, workers
        compared.append(pairs)
        versions = dicom_validators.Versions(None, None, None, {})
        return dicom_validation.Comparison(
            versions, (), len(pairs), unpaired, {}, {}, ()
        )

    monkeypatch.setattr(dicom_validation.Toolset, "find", lambda *_: None)
    monkeypatch.setattr(dicom_validation, "compare", compare)

    status = dicom_validation_command.main(
        [
            "midi",
            "--source",
            str(sources / "option-source" / "source"),
            "--work",
            str(work),
            "--out",
            str(sources / "validation"),
        ]
    )

    assert status != dicom_validation_command.USAGE_ERROR
    assert len(compared[0]) == len(list((work / "release").rglob("*.dcm"))) > 0


def test_a_preset_and_options_together_are_refused(tmp_path):
    with pytest.raises(benchmark.BenchmarkError, match="not both"):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            preset="basic",
            options=[UIDS],
        )
    assert not (tmp_path / "work").exists()


def test_an_option_set_that_cannot_be_composed_is_refused(tmp_path):
    with pytest.raises(PolicyError):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            options=["retain_device_identity", "retain_longitudinal_modified_dates"],
        )
    assert not (tmp_path / "work").exists()


def test_clean_recognizable_visual_features_is_refused(tmp_path):
    with pytest.raises(benchmark.BenchmarkError, match="reviewer's verdict"):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            options=["clean_recognizable_visual_features"],
        )
    assert not (tmp_path / "work").exists()


def test_a_preset_with_clean_recognizable_visual_features_runs_without_it(
    sources, edition
):
    # public-release selects the option, which needs a reviewer's face
    # verdicts; the run takes its other options as the preset composes them.
    assert (
        CLEAN_RECOGNIZABLE_VISUAL_FEATURES in compose_policy("public-release").options
    )
    _, document = _run(
        sources,
        "option",
        preset="public-release",
        tg263_spreadsheet=sources / "edition.xls",
    )

    assert edition == [((), {"spreadsheet": sources / "edition.xls"})]
    versions = document["versions"]
    assert versions["preset"] == "public-release"
    assert versions["left_out"] == [CLEAN_RECOGNIZABLE_VISUAL_FEATURES]
    assert versions["options"] == list(
        compose_preset_without(
            "public-release", CLEAN_RECOGNIZABLE_VISUAL_FEATURES
        ).options
    )
    assert CLEAN_RECOGNIZABLE_VISUAL_FEATURES not in versions["options"]
    assert document["coverage"]["instances"]["released"] > 0


def test_a_preset_without_that_option_leaves_nothing_out(sources):
    _, document = _run(sources, "option", preset="basic")

    assert document["versions"]["left_out"] == []
    assert document["versions"]["safe_private_list"] is None


@pytest.mark.parametrize("chosen", list(SafePrivateList))
def test_the_safe_private_list_is_chosen_and_recorded(sources, chosen):
    _, document = _run(
        sources, "option", options=[SAFE_PRIVATE], safe_private_list=chosen
    )

    assert document["versions"]["safe_private_list"] == chosen.value


def test_tcias_dictionary_without_retain_safe_private_is_refused(tmp_path):
    with pytest.raises(PolicyError, match="Retain Safe Private"):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            options=[UIDS],
            safe_private_list=SafePrivateList.TCIA,
        )


def test_the_command_passes_the_safe_private_list(sources):
    status = midi_benchmark_command.main(
        [
            "run",
            "--source",
            str(_source(sources / "option-source")),
            "--answer-key",
            str(_benchmark_key(sources / "option-source")),
            "--work",
            str(sources / "option"),
            "--option",
            SAFE_PRIVATE,
            "--safe-private-list",
            "tcia",
        ]
    )

    assert status == 0
    document = json.loads((sources / "option" / "benchmark.json").read_text())
    assert document["versions"]["safe_private_list"] == "tcia"


def test_clean_pixel_data_runs_the_text_detector(sources, monkeypatch):
    made = []

    def detector():
        made.append(True)
        return CLEAN_PIXEL_DATA_RUN.finder

    monkeypatch.setattr(benchmark, "TextDetector", detector)
    _, document = _run(sources, "option", options=["clean_pixel_data"])

    assert made == [True]
    # The finder marks every frame, and no reviewer attests a benchmark's
    # regions, so the CT slice is held for review.
    assert document["coverage"]["withheld_reasons"] == {"HeldPixelData": 1}


def test_an_unloadable_text_detector_is_refused(tmp_path, monkeypatch):
    def detector():
        raise TextDetectionError("SYNTHETIC-SECRET-PATH")

    monkeypatch.setattr(benchmark, "TextDetector", detector)
    with pytest.raises(benchmark.BenchmarkError) as raised:
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            options=["clean_pixel_data"],
        )
    assert str(raised.value) == "the pinned text detector could not be loaded"


def test_each_run_writes_each_checks_outcome_in_the_keys_order(sources):
    work, document = _run(sources, "basic")

    outcomes = flips.read_check_outcomes(work / flips.CHECK_OUTCOMES)
    key = read_answer_key(sources / "basic-source" / "key.db")
    assert outcomes.answer_key_sha256 == key.sha256
    assert (outcomes.preset, outcomes.options) == ("basic", ())
    assert len(outcomes.codes) == document["headline"]["checks"]
    letters = outcomes.codes.decode("ascii")
    headline = document["headline"]
    for name in ("passed", "failed", "deliberate", "withheld", "not_in_input"):
        assert letters.count(flips.outcome_code(name).decode()) == headline[name]
    # The CT slice's checks come first, as the key lists them: its Study
    # Description is a deliberate difference, and its Study Date passes.
    assert letters[:2] == "DP"


def test_a_flip_check_of_two_runs_finds_only_the_options_rows_changed(sources):
    basic, _ = _run(sources, "basic")
    option, _ = _run(sources, "option", options=[UIDS])
    # The two keys are the same synthetic key, written twice.
    key = read_answer_key(sources / "basic-source" / "key.db")
    assert read_answer_key(sources / "option-source" / "key.db").sha256 == key.sha256

    document = flips.flip_check(
        key,
        flips.read_check_outcomes(basic / flips.CHECK_OUTCOMES),
        flips.read_check_outcomes(option / flips.CHECK_OUTCOMES),
        UIDS,
    )

    assert document["verdict"] == flips.PASSED
    assert document["checks"]["ungoverned_changed"] == 0
    assert document["changes"] == [
        {
            "governed": True,
            "category": "hipaa HIPAA-R",
            "action": "uid_changed",
            "attribute": "(0008,0018)",
            "reference": "passed",
            "option": "failed",
            "checks": 1,
        }
    ]
    assert document["instances"]["released_in_neither"] == 2
    json.dumps(document)
    assert "| yes | hipaa HIPAA-R | uid_changed | (0008,0018) |" in (
        flips.render_markdown(document)
    )


# Unit tests of the comparison, over a key built in memory.


def _key(*instances):
    return AnswerKey(
        tuple(
            AnswerInstance(
                patient_id=None,
                study_instance_uid=None,
                series_instance_uid=None,
                sop_instance_uid=f"2.25.{number}",
                sop_class_uid=None,
                modality="CT",
                scope=None,
                checks=tuple(
                    parse_check(
                        {
                            "action": f"<{action}>",
                            "tag_ds": place,
                            "answer_category_v2": {"tcia": {"p15": "TEST-CODE"}},
                        }
                    )
                    for action, place in checks
                ),
            )
            for number, checks in enumerate(instances)
        ),
        "0" * 64,
    )


def _outcomes(codes, preset=None, options=(UIDS,), sha256="0" * 64):
    return flips.CheckOutcomes(sha256, preset, tuple(options), codes.encode())


def _basic(codes, **fields):
    return _outcomes(codes, preset="basic", options=(), **fields)


# Study Instance UID is on Retain UIDs' rows; Study Description is not.
_UID = ("uid_changed", "<(0020,000D)>")
_DESCRIPTION = ("text_retained", "<(0008,1030)>")


def test_a_change_off_the_options_rows_fails_the_check():
    key = _key([_UID, _DESCRIPTION])
    document = flips.flip_check(key, _basic("PD"), _outcomes("FP"), UIDS)
    assert document["verdict"] == flips.FAILED
    assert not flips.passed(document)
    assert document["checks"]["ungoverned_changed"] == 1
    # Ungoverned changes come first.
    assert document["changes"][0]["governed"] is False
    assert document["changes"][0]["attribute"] == "(0008,1030)"


def test_an_option_that_changes_none_of_its_checks_has_no_effect():
    key = _key([_UID, _DESCRIPTION])
    document = flips.flip_check(key, _basic("PD"), _outcomes("PD"), UIDS)
    assert document["verdict"] == flips.NO_EFFECT
    assert not flips.passed(document)


def test_an_option_whose_rows_are_not_checked_is_not_exercised():
    key = _key([_DESCRIPTION])
    document = flips.flip_check(key, _basic("D"), _outcomes("D"), UIDS)
    assert document["verdict"] == flips.NOT_EXERCISED
    assert flips.passed(document)


def test_only_instances_that_both_runs_released_are_compared():
    key = _key([_UID, _DESCRIPTION], [_DESCRIPTION], [_UID], [_UID])
    document = flips.flip_check(key, _basic("PDPWW"), _outcomes("FPWPO"), UIDS)
    assert document["instances"] == {
        "released_in_both": 1,
        "released_in_reference_only": 1,
        "released_with_option_only": 1,
        "released_in_neither": 1,
    }
    assert document["checks"]["compared"] == 2
    assert document["checks"]["released_in_reference_only"] == 1
    assert document["checks"]["released_with_option_only"] == 1
    # The description changed only in the instance that both released.
    assert document["checks"]["ungoverned_changed"] == 1


@pytest.mark.parametrize(
    "place",
    [
        # A marker that records the options.
        "<(0012,0064)>[<0000>]<(0008,0100)>",
        # A sequence on the option's rows holds the attribute.
        "<(0008,1140)>[<0000>]<(0008,1150)>",
        # A row that gives the option an action.
        "<(0008,0018)>",
    ],
)
def test_a_check_is_governed_by_its_place(place):
    key = _key([("text_retained", place)])
    document = flips.flip_check(key, _basic("D"), _outcomes("P"), UIDS)
    assert document["verdict"] == flips.PASSED


def test_retain_safe_private_governs_private_attributes():
    key = _key([("text_retained", '<(0019,"SYNTHETIC CREATOR",93)>')])
    document = flips.flip_check(
        key,
        _basic("D"),
        _outcomes("P", options=("retain_safe_private",)),
        "retain_safe_private",
    )
    assert document["verdict"] == flips.PASSED
    assert "(gggg,eeee) where gggg is odd" in flips.governed_entries(
        "retain_safe_private"
    )


def test_supplementary_rules_that_name_the_option_are_governed():
    rules = flips.load_supplementary_actions().rules
    dated = {
        tag
        for tag, rule in rules.items()
        if "retain_longitudinal_full_dates" in rule.options
    }
    assert dated and dated <= flips.governed_entries("retain_longitudinal_full_dates")


@pytest.mark.parametrize(
    "reference, compared, option, message",
    [
        (_outcomes("P"), _outcomes("P"), UIDS, "reference run"),
        (_basic("P"), _basic("P"), UIDS, "compared run"),
        (_basic("P"), _outcomes("P"), "clean_graphics", "Retain options"),
        (_basic("PP"), _outcomes("PP"), UIDS, "not of this answer key"),
        (_basic("P", sha256="1" * 64), _outcomes("P"), UIDS, "not of this answer key"),
    ],
)
def test_runs_that_cannot_be_compared_are_refused(reference, compared, option, message):
    with pytest.raises(flips.FlipCheckError, match=message):
        flips.flip_check(_key([_UID]), reference, compared, option)


def test_check_outcomes_round_trip_and_reject_another_file(tmp_path):
    path = tmp_path / flips.CHECK_OUTCOMES
    flips.write_check_outcomes(path, "0" * 64, compose_custom_policy([UIDS]), b"PFW")
    assert flips.read_check_outcomes(path) == _outcomes("PFW")
    flips.write_check_outcomes(path, "0" * 64, compose_policy("basic"), b"PX")
    with pytest.raises(flips.FlipCheckError, match="not a run's check outcomes"):
        flips.read_check_outcomes(path)
    path.write_bytes(b"not json\nP")
    with pytest.raises(flips.FlipCheckError, match="could not be read"):
        flips.read_check_outcomes(path)


def _flip_command(tmp_path, reference, compared, out):
    key = tmp_path / "key.db"
    if not key.exists():
        key.write_bytes(b"")
    return [
        "flip-check",
        str(key),
        "--reference",
        str(reference),
        "--compared",
        str(compared),
        "--option",
        UIDS,
        "--out",
        str(out),
    ]


def test_the_command_runs_with_an_option_and_compares_two_runs(sources, capsys):
    key = _benchmark_key(sources)
    for name, policy in (
        ("basic", ["--preset", "basic"]),
        ("option", ["--option", UIDS]),
    ):
        assert (
            midi_benchmark_command.main(
                [
                    "run",
                    "--source",
                    str(_source(sources / f"{name}-source")),
                    "--answer-key",
                    str(key),
                    "--work",
                    str(sources / name),
                    *policy,
                ]
            )
            == 0
        )
    capsys.readouterr()
    arguments = [
        "flip-check",
        str(key),
        "--reference",
        str(sources / "basic" / flips.CHECK_OUTCOMES),
        "--compared",
        str(sources / "option" / flips.CHECK_OUTCOMES),
        "--option",
        UIDS,
        "--out",
        str(sources / "flips.json"),
    ]
    assert midi_benchmark_command.main(arguments) == 0
    assert "Verdict: **passed**" in capsys.readouterr().out
    assert json.loads((sources / "flips.json").read_text())["verdict"] == "passed"
    with pytest.raises(SystemExit, match="must not exist"):
        midi_benchmark_command.main(arguments)


def test_the_command_exits_with_one_where_the_check_fails(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        midi_benchmark_command,
        "read_answer_key",
        lambda path: _key([_UID, _DESCRIPTION]),
    )
    reference = tmp_path / "basic.txt"
    compared = tmp_path / "option.txt"
    flips.write_check_outcomes(reference, "0" * 64, compose_policy("basic"), b"PD")
    flips.write_check_outcomes(compared, "0" * 64, compose_custom_policy([UIDS]), b"FP")

    status = midi_benchmark_command.main(
        _flip_command(tmp_path, reference, compared, tmp_path / "out.json")
    )

    assert status == 1
    assert "Verdict: **failed**" in capsys.readouterr().out


def test_the_command_refuses_a_preset_and_an_option_together(tmp_path):
    with pytest.raises(SystemExit):
        midi_benchmark_command.main(
            [
                "run",
                "--source",
                str(tmp_path),
                "--answer-key",
                str(tmp_path / "key.db"),
                "--work",
                str(tmp_path / "work"),
                "--preset",
                "basic",
                "--option",
                UIDS,
            ]
        )
