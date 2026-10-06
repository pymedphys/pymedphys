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
import os
import shutil
import tempfile
import warnings
from pathlib import Path, PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    command,
    diagnostics,
    instance_transform,
    policy,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.policy import compose_policy
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


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """Give a base directory short enough for Windows' path limit.

    On Windows, a run refuses a release directory whose files' paths could
    exceed 259 characters, which pytest's own temporary directories do.
    """
    if os.name != "nt":
        yield tmp_path
        return
    short = Path(tempfile.mkdtemp(prefix="d"))
    yield short
    shutil.rmtree(short, ignore_errors=True)


def _call(  # pylint: disable = too-many-arguments, too-many-positional-arguments
    tmp_path, transform=None, gate=None, source=None, release=None, reporter=None
):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.deidentify_directory(
        source or tmp_path / "source",
        release or tmp_path / "release",
        transform=transform or Transform(),
        gate=gate or Gate(),
        qc_destination=tmp_path / "qc",
        reporter=reporter,
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


def test_a_run_given_a_reporter_publishes_its_release_report(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    reporter = run_report.ReleaseReporter(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )

    status, _, _ = _call(tmp_path, reporter=reporter)

    assert status == command.EXIT_RELEASED
    assert (tmp_path / "release" / run_report.RELEASE_REPORT).is_file()


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


def test_a_dataclass_reason_is_named_with_its_enum_fields(tmp_path):
    # Enum members are defined by the code, so they quote nothing; a release
    # gate's reason gives its decision and code this way.
    _write(tmp_path / "source", synthetic.collection())

    @dataclasses.dataclass(frozen=True)
    class Withheld:
        code: GateReason
        text: str
        missing: GateReason | None = None

    gate = Gate(
        {
            _output(synthetic.PLAN): run.Sequestered(
                (Withheld(GateReason.TEXT_FINDING, SENTINEL),)
            ),
            _output(synthetic.DOSE): run.Sequestered(
                (Withheld(GateReason.TEXT_FINDING, "other"),)
            ),
        }
    )

    status, out, err = _call(tmp_path, gate=gate)

    assert status == command.EXIT_WITHHELD
    assert "Withheld(code=GateReason.TEXT_FINDING): 2" in out
    assert SENTINEL not in out + err


def test_a_dataclass_field_that_nothing_set_is_left_out():
    @dataclasses.dataclass(frozen=True)
    class Withheld:
        code: GateReason
        unset: GateReason = dataclasses.field(init=False)

    reason = Withheld(GateReason.TEXT_FINDING)

    assert command._reason_name(reason) == (  # pylint: disable=protected-access
        "Withheld(code=GateReason.TEXT_FINDING)"
    )


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


def test_a_refused_qc_destination_exits_three_naming_its_check(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    stdout, stderr = io.StringIO(), io.StringIO()

    status = command.deidentify_directory(
        tmp_path / "source",
        tmp_path / "release",
        transform=Transform(),
        gate=Gate(),
        qc_destination=tmp_path / "release" / "qc",
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_NOT_RUN
    assert stderr.getvalue().startswith("error: ")
    assert "details are not shown" not in stderr.getvalue()
    assert not (tmp_path / "release").exists()


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
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
        ],
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
    arguments = parser.parse_args(["in", "out", "--qc-pack", "qc"])
    assert (arguments.source, arguments.release, arguments.qc_pack) == (
        "in",
        "out",
        "qc",
    )


def test_a_failed_run_that_leaves_its_staging_area_says_so(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection())

    def failing_write(file, data):
        raise OSError("no space left")

    monkeypatch.setattr(run, "_write_atomically", failing_write)
    monkeypatch.setattr(run, "_remove", lambda staging: False)

    status, out, err = _call(tmp_path)

    assert status == command.EXIT_STAGING_LEFT
    assert out == ""
    assert "OSError" in err
    assert str(run.staging_path((tmp_path / "release").absolute())) in err
    assert "delete it" in err


def test_a_staging_area_left_by_an_earlier_run_is_not_this_runs(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    run.staging_path((tmp_path / "release").absolute()).mkdir()

    status, _, err = _call(tmp_path)

    assert status == command.EXIT_NOT_RUN
    assert "already exists" in err
    assert "could not be deleted" not in err


def test_reasons_are_counted_once_per_input_by_type(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    @dataclasses.dataclass
    class Place:  # neither frozen nor hashable
        tags: list

    reasons = (Place(["(0010,0010)"]), Place(["(0010,0020)"]), Place([SENTINEL]))
    gate = Gate({_output(synthetic.PLAN): run.Sequestered(reasons)})

    status, out, err = _call(tmp_path, gate=gate)

    assert status == command.EXIT_WITHHELD
    assert "  Place: 1" in out
    assert SENTINEL not in out + err


def test_a_release_name_the_output_cannot_encode_is_escaped(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="ascii", errors="strict")
    release = tmp_path / "rel\u00e9ase"

    status = command.deidentify_directory(
        tmp_path / "source",
        release,
        transform=Transform(),
        gate=Gate(),
        qc_destination=tmp_path / "qc",
        stdout=stdout,
        stderr=io.StringIO(),
    )

    stdout.flush()
    assert status == command.EXIT_RELEASED
    assert b"rel\\xe9ase" in raw.getvalue()
    assert release.is_dir()


def test_source_paths_never_reach_the_output(tmp_path):
    source = tmp_path / f"source-{SENTINEL}"
    names = [f"{index:03d}-{SENTINEL}.dcm" for index in range(6)]
    _write(source, synthetic.collection(), names)
    (source / "DICOMDIR").write_bytes(SENTINEL.encode())

    status, out, err = _call(tmp_path, source=source)

    assert status == command.EXIT_WITHHELD
    assert "released: 6" in out
    assert SENTINEL not in out + err


@pytest.mark.parametrize(
    "extra",
    [
        [f"/data/{SENTINEL}/extra"],
        [f"--{SENTINEL}=/data/{SENTINEL}"],
        ["--", f"/data/{SENTINEL}/extra"],
    ],
    ids=["operand", "option", "after-double-dash"],
)
def test_argument_errors_quote_no_argument(tmp_path, capsys, extra):
    # argparse would repeat an unexpected argument, which can be a source
    # path, in its error message.
    stderr = io.StringIO()

    with pytest.raises(SystemExit) as raised:
        command.main(
            [str(tmp_path / "source"), str(tmp_path / "release"), *extra],
            transform=Transform(),
            gate=Gate(),
            stdout=io.StringIO(),
            stderr=stderr,
        )

    captured = capsys.readouterr()
    assert raised.value.code == command.EXIT_USAGE
    assert stderr.getvalue().startswith("usage: ")
    assert "error: the arguments could not be parsed" in stderr.getvalue()
    assert SENTINEL not in stderr.getvalue() + captured.err + captured.out


def test_help_is_printed_as_usual(capsys):
    with pytest.raises(SystemExit) as raised:
        command.main(["--help"], transform=Transform(), gate=Gate())

    assert raised.value.code == 0
    assert "the release directory to create" in capsys.readouterr().out


def _parsed_call(tmp_path, monkeypatch, *options):
    """Run main with options, and return its status, streams, and call."""
    calls = []

    def recording(*_, **kwargs):
        calls.append(kwargs)
        return command.EXIT_RELEASED

    monkeypatch.setattr(command, "deidentify_directory", recording)
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = [
        str(tmp_path / "source"),
        str(tmp_path / "release"),
        "--qc-pack",
        str(tmp_path / "qc"),
        *options,
    ]
    status = command.main(argv, stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue(), calls


@pytest.fixture(name="enabled")
def _enabled(monkeypatch):
    """Enable the first release's presets, which no release enables yet."""
    monkeypatch.setattr(
        policy, "ENABLED_PRESETS", frozenset({"basic", "basic-clean-descriptors"})
    )


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "options", [(), ("--preset", "basic")], ids=["default", "named"]
)
def test_main_builds_the_basic_transform_and_release_gate(
    tmp_path, monkeypatch, options
):
    status, _, err, calls = _parsed_call(tmp_path, monkeypatch, *options)

    assert (status, err) == (command.EXIT_RELEASED, "")
    (call,) = calls
    assert isinstance(call["transform"], instance_transform.InstanceTransform)
    assert isinstance(call["gate"], instance_transform.ReleaseGate)
    assert call["qc_destination"] == str(tmp_path / "qc")
    assert call["reporter"] is call["transform"].reporter


def test_a_given_transform_runs_without_a_release_report(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        command, "deidentify_directory", lambda *_, **kwargs: calls.append(kwargs)
    )
    command.main(
        ["in", "out", "--qc-pack", str(tmp_path / "qc")],
        transform=Transform(),
        gate=Gate(),
    )

    (call,) = calls
    assert call["reporter"] is None


def test_clean_descriptors_waits_for_its_roi_name_options(capsys):
    # Its transform needs a vocabulary and reviewed-names list, which the
    # command cannot take yet.
    with pytest.raises(SystemExit) as raised:
        command.main(
            ["in", "out", "--qc-pack", "qc", "--preset", "basic-clean-descriptors"]
        )

    assert raised.value.code == command.EXIT_USAGE
    capsys.readouterr()


@pytest.mark.usefixtures("enabled")
def test_each_run_has_a_new_key(tmp_path, monkeypatch):
    _, _, _, first = _parsed_call(tmp_path, monkeypatch)
    _, _, _, second = _parsed_call(tmp_path, monkeypatch)

    keys = [call["transform"]._key for call in first + second]  # pylint: disable = protected-access
    assert keys[0].key_id != keys[1].key_id


def test_a_preset_not_enabled_exits_three_before_anything_runs(tmp_path, monkeypatch):
    # No release enables a preset yet.
    status, out, err, calls = _parsed_call(tmp_path, monkeypatch)

    assert status == command.EXIT_NOT_RUN
    assert (out, calls) == ("", [])
    assert err.startswith("error: ") and "not enabled" in err
    assert not any(tmp_path.iterdir())


def test_an_unknown_preset_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as raised:
        command.main(["in", "out", "--qc-pack", "qc", "--preset", SENTINEL])

    captured = capsys.readouterr()
    assert raised.value.code == command.EXIT_USAGE
    assert SENTINEL not in captured.out + captured.err


@pytest.mark.usefixtures("enabled")
def test_main_runs_the_basic_preset_end_to_end(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    stdout, stderr = io.StringIO(), io.StringIO()

    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_RELEASED, stdout.getvalue() + stderr.getvalue()
    assert (tmp_path / "release" / run_report.RELEASE_REPORT).is_file()
    assert any((tmp_path / "qc").iterdir())
    assert str(tmp_path / "source") not in stdout.getvalue() + stderr.getvalue()
