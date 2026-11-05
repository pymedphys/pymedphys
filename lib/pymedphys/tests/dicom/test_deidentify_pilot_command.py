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

"""The pilot command: a run under a policy that need not be enabled."""

import dataclasses
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import (
    command,
    diagnostics,
    pilot_command,
    policy,
    roi_names,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.keys import DeidKey

from . import _synthetic_references as synthetic
from .test_deidentify_run import SENTINEL, _write

_NOMENCLATURE = tg263.Nomenclature(
    source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
    attribution=tg263.ATTRIBUTION,
    structures=(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Invented",
            minor_category="",
            anatomic_group="",
            primary_name="Lung_L",
            reverse_order_name="L_Lung",
            description="",
            fma_id=None,
        ),
    ),
)
# An instance of an IOD outside the engine's scope, which a run sequesters.
_PDF = "2.25.991"


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """Give a base directory short enough for Windows' path limit."""
    if os.name != "nt":
        yield tmp_path
        return
    short = Path(tempfile.mkdtemp(prefix="d"))
    yield short
    shutil.rmtree(short, ignore_errors=True)


@pytest.fixture(name="temporary")
def _temporary(tmp_path, monkeypatch):
    """Make the command's temporary directory a known one, and return it."""
    made = tmp_path / "temporary"

    def mkdtemp(prefix=None):
        assert prefix == "pymedphys-pilot-"
        made.mkdir(mode=0o700)
        return str(made)

    monkeypatch.setattr(pilot_command.tempfile, "mkdtemp", mkdtemp)
    return made


@pytest.fixture(name="edition")
def _edition(monkeypatch):
    """Serve an invented edition, published for the test, in place of TG-263's."""
    entries = [dataclasses.asdict(s) for s in _NOMENCLATURE.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )
    monkeypatch.setattr(command.tg263_published, "load", lambda **_: _NOMENCLATURE)


def _source(tmp_path, *extra):
    return _write(tmp_path / "source", [*synthetic.collection(), *extra])


def _pilot(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = pilot_command.main(
        [str(each) for each in argv], stdout=stdout, stderr=stderr
    )
    return status, stdout.getvalue(), stderr.getvalue()


def test_nothing_is_enabled_so_the_run_command_refuses_what_the_pilot_runs():
    assert not policy.ENABLED_PRESETS
    assert not policy.ENABLED_OPTIONS


def test_a_pilot_into_a_temporary_directory_prints_counts_and_deletes_it(
    tmp_path, temporary
):
    source = _source(tmp_path)

    status, out, err = _pilot(source, "--preset", "basic")

    assert (status, err) == (pilot_command.EXIT_RELEASED, "")
    assert out.splitlines() == [
        "pilot of the basic preset, which need not be enabled: its release is "
        "for validation only",
        "inputs: 6",
        "  released: 6",
        "release report, sequestered instances by reason:",
        "  none",
        "release report, instances held for review by reason:",
        "  none",
    ]
    assert not temporary.exists()
    assert str(tmp_path) not in out


def test_a_named_release_is_kept_and_its_path_is_not_printed(tmp_path, temporary):
    source = _source(tmp_path)
    release = tmp_path / "release"

    status, out, err = _pilot(source, "--preset", "basic", "--release", release)

    assert (status, err) == (pilot_command.EXIT_RELEASED, "")
    report = json.loads((release / run_report.RELEASE_REPORT).read_text("utf-8"))
    assert report["policy"]["preset"] == "basic"
    assert len(report["released"]) == 6
    # The QC pack was written into the temporary directory, then deleted.
    assert not temporary.exists()
    assert str(tmp_path) not in out


def test_a_named_release_and_qc_pack_need_no_temporary_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot_command.tempfile, "mkdtemp", pytest.fail)
    source = _source(tmp_path)
    release, qc_pack = tmp_path / "release", tmp_path / "qc"

    status, _, err = _pilot(
        source, "--preset", "basic", "--release", release, "--qc-pack", qc_pack
    )

    assert (status, err) == (pilot_command.EXIT_RELEASED, "")
    assert (release / run_report.RELEASE_REPORT).is_file()
    assert any(qc_pack.iterdir())


def _without_a_face_review(preset):
    return not command.face_review_applies(preset)


@pytest.mark.usefixtures("edition", "temporary")
@pytest.mark.parametrize(
    "preset", [each for each in policy.PRESETS if _without_a_face_review(each)]
)
def test_every_preset_runs_though_none_is_enabled(tmp_path, preset):
    source = _source(tmp_path)
    release = tmp_path / "release"
    held = ["--empty-held-roi-names"] if command.roi_name_options_apply(preset) else []

    status, out, _ = _pilot(source, "--preset", preset, "--release", release, *held)

    assert status in (pilot_command.EXIT_RELEASED, pilot_command.EXIT_WITHHELD), out
    assert out.startswith(f"pilot of the {preset} preset")
    report = json.loads((release / run_report.RELEASE_REPORT).read_text("utf-8"))
    assert report["policy"]["preset"] == preset
    assert report["policy"]["options"] == list(policy.PRESETS[preset])


@pytest.mark.usefixtures("temporary")
def test_a_custom_option_set_runs_though_it_is_not_enabled(tmp_path):
    source = _source(tmp_path)
    release = tmp_path / "release"

    status, out, err = _pilot(
        source,
        "--option",
        "retain_uids",
        "--option",
        "retain_longitudinal_full_dates",
        "--release",
        release,
    )

    assert (status, err) == (pilot_command.EXIT_RELEASED, ""), out
    assert out.startswith(
        "pilot of the custom option set retain_longitudinal_full_dates, retain_uids,"
    )
    report = json.loads((release / run_report.RELEASE_REPORT).read_text("utf-8"))
    assert report["policy"]["preset"] is None
    assert report["policy"]["options"] == [
        "retain_uids",
        "retain_longitudinal_full_dates",
    ]


@pytest.mark.usefixtures("temporary")
def test_sequestered_instances_are_counted_by_the_release_reports_reasons(tmp_path):
    pdf = synthetic.instance(
        synthetic.ENCAPSULATED_PDF_STORAGE, _PDF, synthetic.OTHER_SERIES
    )
    source = _source(tmp_path, pdf)

    status, out, _ = _pilot(source, "--preset", "basic")

    assert status == pilot_command.EXIT_WITHHELD
    lines = out.splitlines()
    assert "  sequestered: 1" in lines
    start = lines.index("release report, sequestered instances by reason:")
    assert lines[start + 1].startswith("  stage=scope code=unsupported-iod iod=")
    assert lines[start + 1].endswith(": 1")
    assert "S-0001" not in out


def _result(release, *statuses):
    return run.RunResult(
        release=release,
        outcomes=tuple(
            run.Outcome(position, status) for position, status in enumerate(statuses)
        ),
        findings=(),
    )


def test_pilot_lines_count_each_reason_of_the_report_and_name_no_label(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    walker = {
        "stage": "walker",
        "code": "unwritable",
        "attribute": "(0010,0010)",
        "action": "X",
        "vr": None,
    }
    gate = {"stage": "release", "code": "direct-identifier"}
    document = {
        "sequestered": [
            {"label": "S-0001", "reasons": [walker, gate]},
            {"label": "S-0002", "reasons": [gate]},
        ],
        "held_for_review": [
            {"stage": "descriptors", "code": "unreviewed", "count": 3},
        ],
    }
    (release / run_report.RELEASE_REPORT).write_text(json.dumps(document), "utf-8")
    result = _result(release, *[run.Status.SEQUESTERED] * 2, run.Status.RELEASED)

    lines = pilot_command.pilot_lines(result, diagnostics.RedactionCounts())

    assert lines == [
        "inputs: 3",
        "  released: 1",
        "  sequestered: 2",
        "release report, sequestered instances by reason:",
        "  stage=release code=direct-identifier: 2",
        "  stage=walker code=unwritable attribute=(0010,0010) action=X: 1",
        "release report, instances held for review by reason:",
        "  stage=descriptors code=unreviewed: 3",
    ]
    assert not any("S-000" in line or str(tmp_path) in line for line in lines)


@pytest.mark.parametrize("content", [None, "not json", "[]", '{"sequestered": 1}'])
def test_a_report_that_cannot_be_read_is_said_so_without_its_content(tmp_path, content):
    release = tmp_path / "release"
    release.mkdir()
    if content is not None:
        (release / run_report.RELEASE_REPORT).write_text(content, "utf-8")

    lines = pilot_command.pilot_lines(
        _result(release, run.Status.RELEASED), diagnostics.RedactionCounts()
    )

    # A report that is not a JSON object cannot say whether the run is ready
    # either, and the command's summary says so.
    unknown = [
        "readiness for release: unknown, since the release report's readiness "
        "could not be read"
    ]
    assert lines == [
        "inputs: 1",
        "  released: 1",
        *(unknown if content in ("not json", "[]") else []),
        "release report: could not be read, so its reason counts are not shown",
    ]


def test_a_run_that_cannot_start_names_its_directories_by_placeholder(
    tmp_path, temporary
):
    source = _source(tmp_path)
    release = tmp_path / SENTINEL
    release.mkdir()

    status, out, err = _pilot(source, "--preset", "basic", "--release", release)

    assert status == pilot_command.EXIT_NOT_RUN
    assert "the release directory RELEASE already exists" in err
    assert SENTINEL not in out + err
    assert not temporary.exists()


class _Broken(io.StringIO):
    def write(self, s):
        raise BrokenPipeError


def test_a_failing_error_stream_still_deletes_the_temporary_directory(
    tmp_path, temporary
):
    source = _source(tmp_path)
    release = tmp_path / "release"
    release.mkdir()

    with pytest.raises(BrokenPipeError):
        pilot_command.main(
            [str(source), "--preset", "basic", "--release", str(release)],
            stdout=io.StringIO(),
            stderr=_Broken(),
        )

    assert not temporary.exists()


def test_a_qc_pack_given_with_a_tilde_is_named_by_placeholder(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    source = _source(tmp_path)

    def refused(*_):
        raise OSError("refused")

    # The release cannot be published, and its QC pack cannot be withdrawn.
    monkeypatch.setattr(run.os, "rename", refused)
    monkeypatch.setattr(run.qc_store, "withdraw_qc_pack", lambda *_: False)

    status, out, err = _pilot(
        source,
        "--preset",
        "basic",
        "--release",
        tmp_path / "release",
        "--qc-pack",
        f"~/{SENTINEL}",
    )

    assert status == pilot_command.EXIT_NOT_RUN
    assert "the QC pack in QC-PACK could not be removed" in err
    assert SENTINEL not in out + err
    assert str(home) not in out + err


def test_a_temporary_directory_left_behind_is_named_so_it_can_be_deleted(
    tmp_path, temporary, monkeypatch
):
    source = _source(tmp_path)
    monkeypatch.setattr(pilot_command.shutil, "rmtree", lambda *_, **__: None)

    status, _, err = _pilot(source, "--preset", "basic")

    assert status == pilot_command.EXIT_STAGING_LEFT
    assert f"the temporary directory {temporary} could not be deleted" in err


def test_a_transform_that_cannot_be_built_runs_nothing(tmp_path, temporary):
    source = _source(tmp_path)

    status, out, err = _pilot(
        source, "--preset", "basic", "--safe-private-list", "tcia"
    )

    assert (status, out) == (pilot_command.EXIT_NOT_RUN, "")
    assert err.startswith("error: a safe private list can be chosen only")
    assert not temporary.exists()


def test_clean_recognizable_visual_features_needs_a_face_review(tmp_path, temporary):
    source = _source(tmp_path)

    status, out, err = _pilot(source, "--option", "clean_recognizable_visual_features")

    assert (status, out) == (pilot_command.EXIT_NOT_RUN, "")
    assert "needs a face review" in err
    assert not temporary.exists()


@pytest.mark.parametrize(
    "options",
    [
        ("--preset", "basic", "--empty-held-roi-names"),
        ("--preset", "tps-import", "--region-rules", "rules.toml"),
        ("--option", "clean_pixel_data", "--face-review", "qc"),
    ],
    ids=["roi-names", "region-rules", "face-review"],
)
def test_inputs_for_an_option_not_selected_are_a_usage_error(
    tmp_path, monkeypatch, options
):
    monkeypatch.setattr(pilot_command.tempfile, "mkdtemp", pytest.fail)

    status, out, err = _pilot(tmp_path / "source", *options)

    assert (status, out) == (pilot_command.EXIT_USAGE, "")
    assert err.startswith("error: --") and "only under" in err


@pytest.mark.parametrize(
    "argv",
    [[SENTINEL], [SENTINEL, "--preset", SENTINEL], [SENTINEL, "--option", "x"]],
    ids=["no-policy", "unknown-preset", "unknown-option"],
)
def test_argument_errors_quote_no_argument(capsys, argv):
    with pytest.raises(SystemExit) as raised:
        pilot_command.main(argv)

    captured = capsys.readouterr()
    assert raised.value.code == pilot_command.EXIT_USAGE
    assert SENTINEL not in captured.out + captured.err


def test_the_run_command_still_refuses_a_policy_that_is_not_enabled(tmp_path):
    with pytest.raises(command.TransformNotBuilt, match="not enabled"):
        command.transform_for(
            "basic",
            DeidKey.generate(),
            source=tmp_path / "source",
            release=tmp_path / "release",
            qc_pack=tmp_path / "qc",
        )


def test_an_unvalidated_policy_is_a_preset_or_an_option_set_not_both():
    with pytest.raises(policy.PolicyError, match="not both"):
        command.build_transform(
            "basic",
            DeidKey.generate(),
            options=["retain_uids"],
            unvalidated_policy=True,
        )
