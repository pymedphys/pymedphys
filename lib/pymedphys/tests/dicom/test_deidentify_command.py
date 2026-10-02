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

"""The de-identification command line's entry point."""

import dataclasses
import io
import logging
import warnings
from pathlib import Path, PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import command, diagnostics, run
from pymedphys._dicom.deidentify.reference_graph import Finding, FindingKind

from . import _synthetic_references as synthetic
from .test_deidentify_run import (
    SENTINEL,
    Gate,
    GateReason,
    Transform,
    _output,
    _write,
)


def _call(tmp_path, transform=None, gate=None, source=None, release=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.deidentify_directory(
        source or tmp_path / "source",
        release or tmp_path / "release",
        transform=transform or Transform(),
        gate=gate or Gate(),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


def test_a_clean_run_exits_zero_and_summarises_by_status(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    status, out, err = _call(tmp_path)

    assert status == command.EXIT_RELEASED == 0
    assert "inputs: 6" in out
    assert "released: 6" in out
    assert "sequestered" not in out
    assert err == ""
    assert (tmp_path / "release").is_dir()


def test_a_withheld_input_exits_one_and_names_reasons_by_type(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    gate = Gate(
        {_output(synthetic.PLAN): run.HoldForReview((GateReason.TEXT_FINDING,))}
    )
    transform = Transform(sequester={synthetic.DOSE})

    status, out, _ = _call(tmp_path, transform, gate)

    assert status == command.EXIT_WITHHELD == 1
    assert "released: 4" in out
    assert "held-for-review: 1" in out
    assert "sequestered: 1" in out
    assert "GateReason.TEXT_FINDING: 2" in out


def test_a_dataclass_reason_is_named_by_its_type_alone(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    @dataclasses.dataclass(frozen=True)
    class Residual:
        text: str

    gate = Gate({_output(synthetic.PLAN): run.Sequestered((Residual(SENTINEL),))})

    status, out, err = _call(tmp_path, gate=gate)

    assert status == command.EXIT_WITHHELD
    assert "Residual: 1" in out
    assert SENTINEL not in out + err


def test_refused_inputs_and_findings_are_counted(tmp_path):
    source = _write(tmp_path / "source", synthetic.collection())
    (source / "DICOMDIR").write_bytes(b"not read")
    dose = synthetic.rt_dose()
    dose.SOPInstanceUID = synthetic.PLAN  # conflicts with the plan
    _write(source, [dose], ["999.dcm"])

    status, out, _ = _call(tmp_path)

    assert status == command.EXIT_WITHHELD
    assert "refused: 1" in out
    assert "RunReason.DICOMDIR: 1" in out
    assert "FindingKind.CONFLICTING_INSTANCE: 1" in out


def test_an_empty_source_publishes_an_empty_release(tmp_path):
    (tmp_path / "source").mkdir()

    status, out, _ = _call(tmp_path)

    assert status == command.EXIT_RELEASED
    assert "inputs: 0" in out
    assert (tmp_path / "release").is_dir()


def test_a_run_that_cannot_start_exits_three_naming_no_source_path(tmp_path):
    source = tmp_path / f"missing-{SENTINEL}"

    status, out, err = _call(tmp_path, source=source)

    assert status == command.EXIT_NOT_RUN == 3
    assert out == ""
    assert "the source is not a directory" in err
    assert SENTINEL not in err


def test_an_existing_release_directory_exits_three(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    (tmp_path / "release").mkdir()

    status, _, err = _call(tmp_path)

    assert status == command.EXIT_NOT_RUN
    assert "already exists" in err


def test_a_stopped_run_exits_three_and_writes_nothing(tmp_path):
    other = synthetic.ct_slice(1)
    other.PatientID = "SYNTHETIC-9X4M"
    _write(tmp_path / "source", [synthetic.ct_slice(0), other])

    status, out, err = _call(tmp_path)

    assert status == command.EXIT_NOT_RUN
    assert out == ""
    assert "several patients" in err
    assert not (tmp_path / "release").exists()


def test_staging_left_behind_exits_four_and_says_so(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection())
    monkeypatch.setattr(run, "_remove", lambda staging: False)

    status, out, err = _call(tmp_path)

    assert status == command.EXIT_STAGING_LEFT == 4
    assert "released: 6" in out
    assert str(run.staging_path((tmp_path / "release").absolute())) in err
    assert "delete it" in err


def test_staging_left_behind_outranks_withheld_inputs(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection())
    monkeypatch.setattr(run, "_remove", lambda staging: False)

    status, _, _ = _call(tmp_path, Transform(sequester={synthetic.DOSE}))

    assert status == command.EXIT_STAGING_LEFT


def test_an_unexpected_error_exits_seventy_with_its_type_alone(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection())

    def failing(*args, **kwargs):
        raise ValueError(f"cannot handle {SENTINEL}")

    monkeypatch.setattr(run, "run", failing)

    status, out, err = _call(tmp_path)

    assert status == command.EXIT_INTERNAL_ERROR == 70
    assert out == ""
    assert "ValueError" in err
    assert SENTINEL not in err


def test_diagnostics_are_redacted_and_counted(tmp_path, caplog):
    _write(tmp_path / "source", synthetic.collection())

    def noisy(data, record):
        warnings.warn(f"bad value {SENTINEL}", UserWarning, stacklevel=1)
        logging.getLogger("pydicom.pixels").warning("bad value %s", SENTINEL)
        return Transform()(data, record)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG):
            status, out, err = _call(tmp_path, transform=noisy)

    assert status == command.EXIT_RELEASED
    assert "redacted diagnostics: 6 warnings, 6 log records" in out
    assert [str(warning.message) for warning in caught] == [
        diagnostics.WARNING_SUMMARY
    ] * 6
    assert all(SENTINEL not in record.getMessage() for record in caplog.records)
    assert SENTINEL not in out + err


def test_no_redaction_line_when_nothing_was_redacted(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    _, out, _ = _call(tmp_path)

    assert "redacted" not in out


def test_summary_lines_name_no_path_or_value():
    result = run.RunResult(
        release=Path("/release"),
        outcomes=(
            run.Outcome(0, run.Status.RELEASED, (), PurePosixPath("a/b.dcm")),
            run.Outcome(1, run.Status.DUPLICATE, (), PurePosixPath("a/b.dcm"), 0),
            run.Outcome(2, run.Status.SEQUESTERED, (FindingKind.MISSING_IDENTIFIER,)),
        ),
        findings=(Finding(FindingKind.MISSING_IDENTIFIER, ((2,),), ("(0020,000D)",)),),
    )

    lines = command.summary_lines(result, diagnostics.RedactionCounts())

    assert lines == [
        f"release directory: {result.release}",
        "inputs: 3",
        "  released: 1",
        "  duplicate: 1",
        "  sequestered: 1",
        "reasons inputs were withheld:",
        "  FindingKind.MISSING_IDENTIFIER: 1",
        "first-pass findings:",
        "  FindingKind.MISSING_IDENTIFIER: 1",
    ]


@pytest.mark.parametrize(
    "statuses, expected",
    [
        ((), command.EXIT_RELEASED),
        ((run.Status.RELEASED, run.Status.DUPLICATE), command.EXIT_RELEASED),
        ((run.Status.RELEASED, run.Status.REFUSED), command.EXIT_WITHHELD),
        ((run.Status.HELD_FOR_REVIEW,), command.EXIT_WITHHELD),
        ((run.Status.SEQUESTERED,), command.EXIT_WITHHELD),
    ],
)
def test_exit_status_follows_outcomes(statuses, expected):
    result = run.RunResult(
        release=Path("/release"),
        outcomes=tuple(
            run.Outcome(position, status) for position, status in enumerate(statuses)
        ),
        findings=(),
    )

    assert command.exit_status(result) == expected


def test_main_parses_source_and_release(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    stdout = io.StringIO()

    status = command.main(
        [str(tmp_path / "source"), str(tmp_path / "release")],
        transform=Transform(),
        gate=Gate(),
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert status == command.EXIT_RELEASED
    assert "released: 6" in stdout.getvalue()


def test_main_rejects_missing_arguments_with_usage_status(capsys):
    with pytest.raises(SystemExit) as raised:
        command.main([], transform=Transform(), gate=Gate())

    assert raised.value.code == command.EXIT_USAGE == 2
    assert "usage" in capsys.readouterr().err


def test_build_parser_takes_a_program_name():
    parser = command.build_parser(prog="pymedphys dicom deidentify")

    assert parser.prog == "pymedphys dicom deidentify"
    arguments = parser.parse_args(["in", "out"])
    assert (arguments.source, arguments.release) == ("in", "out")
