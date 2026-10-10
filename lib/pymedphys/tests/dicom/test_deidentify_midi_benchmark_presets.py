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

"""Tests of the MIDI benchmark under a preset with Clean Descriptors (D-018).

The TG-263 edition is an invented one, published for the tests; every DICOM
file and answer key is synthetic, as in ``test_deidentify_midi_benchmark``.
"""

import dataclasses
import enum

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_command, roi_names, run
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.midi_answer_key import parse_check
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._nomenclature import tg263

from .test_deidentify_descriptor_cleaning import _NOMENCLATURE
from .test_deidentify_midi_benchmark import CT_IOD, _benchmark_key, _source

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)


@pytest.fixture(name="edition")
def _edition(monkeypatch):
    """Serve an invented edition, published for the test, in place of TG-263's."""
    entries = [dataclasses.asdict(s) for s in _NOMENCLATURE.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )
    loads = []

    def load(*args, **kwargs):
        loads.append((args, kwargs))
        return _NOMENCLATURE

    monkeypatch.setattr(benchmark.tg263_published, "load", load)
    return loads


def test_a_preset_with_clean_descriptors_cleans_and_scores(tmp_path, edition):
    document = benchmark.run_benchmark(
        _source(tmp_path),
        _benchmark_key(tmp_path),
        tmp_path / "work",
        preset="basic-clean-descriptors",
        tg263_spreadsheet=tmp_path / "edition.xls",
    ).document

    assert edition == [((), {"spreadsheet": tmp_path / "edition.xls"})]
    assert document["versions"]["preset"] == "basic-clean-descriptors"
    assert "held names emptied" in document["versions"]["roi_names"]
    assert document["coverage"]["instances"]["released"] == 2
    # Study Description takes C, which the option leaves to the policy
    # without it, so its X explains the failure, as under basic.
    assert document["deliberate_differences"] == [
        {
            "category": "tcia TEST-RETAIN-DESCRIPTION",
            "action": "text_retained",
            "attribute": "(0008,1030)",
            "policy_action": "X",
            "checks": 1,
        }
    ]


def test_a_tag_retained_failure_takes_the_fallback_action_under_the_option():
    check = parse_check({"action": "<tag_retained>", "tag_ds": "<(0008,1030)>"})
    policy = compose_policy("basic-clean-descriptors")
    scored = benchmark.score_check(
        check,
        pydicom.Dataset(),
        benchmark.IdentifierMapping({}, {}),
        ElementRules(policy),
        load_iod_tables().iods[CT_IOD],
        fallback=ElementRules(compose_policy("basic")),
    )
    assert scored == benchmark.Scored(benchmark.Result.FAILED, "X", deliberate=True)
    without = benchmark.score_check(
        check,
        pydicom.Dataset(),
        benchmark.IdentifierMapping({}, {}),
        ElementRules(policy),
        load_iod_tables().iods[CT_IOD],
    )
    assert without == benchmark.Scored(benchmark.Result.FAILED)


def test_an_unloadable_edition_is_refused_before_the_run(tmp_path, monkeypatch):
    def load(*_, **__):
        raise OSError("SYNTHETIC-SECRET-PATH")

    monkeypatch.setattr(benchmark.tg263_published, "load", load)
    with pytest.raises(benchmark.BenchmarkError) as raised:
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            preset="basic-clean-descriptors",
        )
    assert str(raised.value) == "the pinned TG-263 edition could not be loaded"
    assert not (tmp_path / "work").exists()


def test_a_spreadsheet_without_clean_descriptors_is_refused(tmp_path):
    with pytest.raises(benchmark.BenchmarkError, match="only to a preset"):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            tg263_spreadsheet=tmp_path / "edition.xls",
        )


def test_the_command_takes_a_tg263_spreadsheet(tmp_path, edition, capsys):
    assert (
        midi_benchmark_command.main(
            [
                "run",
                "--source",
                str(_source(tmp_path)),
                "--answer-key",
                str(_benchmark_key(tmp_path)),
                "--work",
                str(tmp_path / "work"),
                "--preset",
                "basic-clean-descriptors",
                "--tg263",
                str(tmp_path / "edition.xls"),
            ]
        )
        == 0
    )

    assert edition == [((), {"spreadsheet": tmp_path / "edition.xls"})]
    assert "| roi_names | cleaned with " in capsys.readouterr().out


def test_a_withheld_instance_is_described_by_status_and_reasons():
    # pylint: disable = protected-access
    class Reason(enum.Enum):
        HELD = "test-held-reason"

    header = benchmark._Header(
        patient_id=None,
        study=None,
        series=None,
        instance=None,
        sop_class="1.2.840.10008.5.1.4.1.1.481.3",
        transfer_syntax="1.2.3.4",
    )
    outcome = run.Outcome(0, run.Status.HELD_FOR_REVIEW, (Reason.HELD, Reason.HELD))
    assert benchmark._not_released(benchmark.Context.WITHHELD, header, outcome) == (
        "withheld: held-for-review",
        "test-held-reason",
        "RT Structure Set Storage",
        "other",
    )
