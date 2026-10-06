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

"""The de-identification library's entry point."""

import dataclasses
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._nomenclature import roi_list, tg263

from pymedphys._dicom.deidentify import (
    api,
    command,
    diagnostics,
    instance_transform,
    policy,
    roi_names,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)

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
_CLEAN = "basic-clean-descriptors"


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


@pytest.fixture(name="enabled")
def _enabled(monkeypatch):
    """Enable the first release's presets, which no release enables yet."""
    monkeypatch.setattr(
        policy, "ENABLED_PRESETS", frozenset({"basic", "basic-clean-descriptors"})
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

    monkeypatch.setattr(command.tg263_published, "load", load)
    return loads


def _deidentify(tmp_path, **options):
    return api.deidentify(
        tmp_path / "source", tmp_path / "release", qc_pack=tmp_path / "qc", **options
    )


@pytest.mark.usefixtures("enabled")
def test_the_basic_preset_releases_a_collection_with_its_report(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    done = _deidentify(tmp_path)

    assert done.released, done.summary()
    assert done.exit_status == command.EXIT_RELEASED
    assert done.result.release == (tmp_path / "release").absolute()
    assert len(done.result.outcomes) == 6
    assert (tmp_path / "release" / run_report.RELEASE_REPORT).is_file()
    assert any((tmp_path / "qc").iterdir())
    assert done.summary()[1] == "inputs: 6"
    assert str(tmp_path / "source") not in "\n".join(done.summary())


@pytest.mark.usefixtures("enabled", "edition")
def test_clean_descriptors_runs_with_the_reviewed_names_list(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    path = tmp_path / "custodian" / "reviewed.json"
    path.parent.mkdir()
    reviewed = ReviewedNames.open(path)
    reviewed.record("PTV boost", ReviewedName(Review.KEEP))
    reviewed.save()

    done = _deidentify(
        tmp_path, preset=_CLEAN, reviewed_names=path, empty_held_roi_names=True
    )

    assert done.released, done.summary()
    assert (tmp_path / "release" / run_report.RELEASE_REPORT).is_file()


def _recorded_run(monkeypatch):
    """Record run.run's arguments in place of running it."""
    calls = []

    def recording(discovery, release, transform, gate, **kwargs):
        calls.append(
            (Path(release), type(transform), type(gate), kwargs, transform, discovery)
        )
        return run.RunResult(release=Path(release), outcomes=(), findings=())

    monkeypatch.setattr(run, "run", recording)
    return calls


@pytest.mark.usefixtures("enabled", "edition")
@pytest.mark.parametrize("preset", ["basic", _CLEAN])
def test_the_library_runs_as_the_command_line_does(tmp_path, monkeypatch, preset):
    calls = _recorded_run(monkeypatch)
    (tmp_path / "source").mkdir()
    options = ["--empty-held-roi-names"] if preset == _CLEAN else []

    command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--preset",
            preset,
            *options,
        ]
    )
    api.deidentify(
        str(tmp_path / "source"),
        str(tmp_path / "release"),
        qc_pack=str(tmp_path / "qc"),
        preset=preset,
        empty_held_roi_names=preset == _CLEAN,
    )

    (by_command, by_library) = [call[:3] for call in calls]
    assert by_command == by_library
    assert by_library[1] is instance_transform.InstanceTransform
    assert by_library[2] is instance_transform.ReleaseGate
    command_kwargs, library_kwargs = calls[0][3], calls[1][3]
    assert command_kwargs.keys() == library_kwargs.keys()
    assert library_kwargs["qc_destination"] == str(tmp_path / "qc")
    transform = calls[1][4]
    assert library_kwargs["reporter"] is transform.reporter
    assert transform._key.key_id != calls[0][4]._key.key_id  # pylint: disable = protected-access


@pytest.mark.usefixtures("enabled")
def test_each_run_has_a_new_key(tmp_path, monkeypatch):
    calls = _recorded_run(monkeypatch)
    (tmp_path / "source").mkdir()

    _deidentify(tmp_path)
    _deidentify(tmp_path)

    first, second = (call[4]._key for call in calls)  # pylint: disable = protected-access
    assert first.key_id != second.key_id


def test_a_preset_not_enabled_raises_before_anything_is_created(tmp_path):
    # No release enables a preset yet.
    with pytest.raises(api.DeidentifyError, match="not enabled"):
        _deidentify(tmp_path)

    assert not any(tmp_path.iterdir())


def test_clean_descriptors_not_enabled_raises_before_loading_anything(
    tmp_path, edition
):
    with pytest.raises(api.DeidentifyError, match="not enabled"):
        _deidentify(tmp_path, preset=_CLEAN)

    assert edition == []


def test_an_unknown_preset_raises(tmp_path):
    with pytest.raises(api.DeidentifyError):
        _deidentify(tmp_path, preset="invented")

    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "option",
    [
        {"tg263_spreadsheet": "x"},
        {"reviewed_names": "x"},
        {"empty_held_roi_names": True},
        {"roi_list": "x"},
    ],
    ids=lambda option: next(iter(option)),
)
def test_roi_name_options_without_clean_descriptors_are_refused(
    tmp_path, edition, option
):
    with pytest.raises(ValueError, match="basic-clean-descriptors"):
        _deidentify(tmp_path, **option)

    assert edition == []
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled", "edition")
def test_a_given_spreadsheet_is_read_in_place_of_the_download(
    tmp_path, monkeypatch, edition
):
    _recorded_run(monkeypatch)
    (tmp_path / "source").mkdir()
    spreadsheet = tmp_path / "tg263.xlsx"

    _deidentify(tmp_path, preset=_CLEAN, tg263_spreadsheet=spreadsheet)

    assert edition == [((), {"spreadsheet": spreadsheet})]


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "failure", [tg263.TG263Error(SENTINEL), OSError(SENTINEL)], ids=["pin", "os"]
)
def test_an_edition_that_cannot_be_loaded_raises_naming_no_path(
    tmp_path, monkeypatch, failure
):
    def load(*_, **__):
        raise failure

    monkeypatch.setattr(command.tg263_published, "load", load)

    with pytest.raises(api.DeidentifyError) as raised:
        _deidentify(tmp_path, preset=_CLEAN)

    assert str(raised.value).startswith("the TG-263 edition")
    assert SENTINEL not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled", "edition")
@pytest.mark.parametrize("where", ["custodian", "release", "qc", "source"])
def test_a_reviewed_names_list_that_cannot_be_used_raises_naming_no_path(
    tmp_path, where
):
    path = tmp_path / where / SENTINEL
    path.parent.mkdir()
    ReviewedNames.open(path).save()
    if where == "custodian":
        path = tmp_path / where / "missing.json"
    before = sorted(tmp_path.rglob("*"))

    with pytest.raises(api.DeidentifyError) as raised:
        _deidentify(tmp_path, preset=_CLEAN, reviewed_names=path)

    message = str(raised.value)
    expected = "does not exist" if where == "custodian" else "could not be used"
    assert message.startswith("the reviewed-names list") and expected in message
    assert SENTINEL not in message and str(tmp_path) not in message
    assert sorted(tmp_path.rglob("*")) == before


def _converted_list(path, *names):
    source = path.parent / "list.csv"
    source.write_text("Name\n" + "".join(f"{name}\n" for name in names), "utf-8")
    path.write_text(roi_list.to_json(roi_list.read_csv(source, version="1")), "utf-8")


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.usefixtures("enabled", "edition")
def test_an_institutional_list_is_used_as_the_command_line_uses_it(
    tmp_path, monkeypatch
):
    calls = _recorded_run(monkeypatch)
    (tmp_path / "source").mkdir()
    path = tmp_path / "lists" / "institutional.json"
    path.parent.mkdir()
    _converted_list(path, "ClinicX_Lung")

    command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--preset",
            _CLEAN,
            "--roi-list",
            str(path),
        ]
    )
    _deidentify(tmp_path, preset=_CLEAN, roi_list=path)

    # pylint: disable-next = protected-access
    by_command, by_library = (call[4]._cleaning for call in calls)
    assert by_library.institutional == by_command.institutional
    assert by_library.institutional == roi_list.load_json(path)


@pytest.mark.usefixtures("enabled", "edition")
@pytest.mark.parametrize("problem", ["missing", "not json"])
def test_an_institutional_list_that_cannot_be_used_raises_naming_no_path(
    tmp_path, problem
):
    path = tmp_path / "lists" / f"{SENTINEL}.json"
    path.parent.mkdir()
    if problem == "not json":
        path.write_text(SENTINEL, "utf-8")
    before = sorted(tmp_path.rglob("*"))

    with pytest.raises(api.DeidentifyError) as raised:
        _deidentify(tmp_path, preset=_CLEAN, roi_list=path)

    message = str(raised.value)
    assert message.startswith("the institutional list of ROI names")
    assert SENTINEL not in message and str(tmp_path) not in message
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.usefixtures("enabled")
def test_a_run_that_cannot_start_raises_the_runs_own_error(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    (tmp_path / "release").mkdir()

    with pytest.raises(run.RunError):
        _deidentify(tmp_path)


@pytest.mark.parametrize(
    "statuses, released, status",
    [
        ((run.Status.RELEASED, run.Status.DUPLICATE), True, command.EXIT_RELEASED),
        ((run.Status.RELEASED, run.Status.SEQUESTERED), False, command.EXIT_WITHHELD),
        ((run.Status.HELD_FOR_REVIEW,), False, command.EXIT_WITHHELD),
    ],
)
def test_released_follows_outcomes(statuses, released, status):
    result = run.RunResult(
        release=Path("/release"),
        outcomes=tuple(
            run.Outcome(position, status) for position, status in enumerate(statuses)
        ),
        findings=(),
    )

    done = api.Deidentified(result, diagnostics.RedactionCounts())

    assert (done.released, done.exit_status) == (released, status)


def test_a_staging_area_left_behind_is_not_released():
    result = run.RunResult(
        release=Path("/release"),
        outcomes=(run.Outcome(0, run.Status.RELEASED),),
        findings=(),
        staging_removed=False,
    )

    done = api.Deidentified(result, diagnostics.RedactionCounts())

    assert not done.released
    assert done.exit_status == command.EXIT_STAGING_LEFT
