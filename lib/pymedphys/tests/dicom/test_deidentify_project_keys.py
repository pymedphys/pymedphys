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

"""Runs under a project key and its subject profiles (D-004)."""

import base64
import datetime
import io
import json
import os
import pathlib
import stat

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    conformance,
    conformance_markdown,
    dates,
    key_command,
    keys,
    modified_dates,
    policy,
    profiles,
    release_report,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.policy import MODIFIED_DATES, compose_custom_policy
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue

from . import _synthetic_references as synthetic
from .test_deidentify_run import _write

KEY = keys.DeidKey(bytes(range(32)))
OTHER_KEY = keys.DeidKey(bytes(range(1, 33)))
SUBJECT = SubjectIdentity.from_patient_id(synthetic.PATIENT_ID)
_STUDY_DATE = "20261004"

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    """Keep the PyMedPhys configuration directory inside the test's own."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture(name="enabled")
def fixture_enabled(monkeypatch):
    """Enable the basic preset, Modified Dates, and project keys for a test."""
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(policy, "ENABLED_OPTIONS", frozenset({MODIFIED_DATES}))
    monkeypatch.setattr(keys, "PROJECT_KEYS_ENABLED", True)


@pytest.fixture(name="custodian")
def fixture_custodian(tmp_path):
    """A project key file and the path of its store, outside every run's directories."""
    directory = tmp_path / "custodian"
    directory.mkdir()
    key_file = keys.write_key_file(directory / "key.json", keys.DeidKey.generate())
    return key_file, directory / "profiles.json"


def _moved(source, weeks):
    moved = datetime.date.fromisoformat(source) - datetime.timedelta(weeks=weeks)
    return moved.strftime("%Y%m%d")


def _slices(*numbers):
    datasets = []
    for number in numbers:
        dataset = synthetic.ct_slice(number)
        dataset.StudyDate = _STUDY_DATE
        datasets.append(dataset)
    return datasets


def _run(tmp_path, name, datasets, custodian, **options):
    _write(tmp_path / name / "source", datasets)
    key_file, store = custodian
    return api.deidentify(
        tmp_path / name / "source",
        tmp_path / name / "release",
        qc_pack=tmp_path / name / "qc",
        options=[MODIFIED_DATES],
        key_file=key_file,
        profile_store=store,
        **options,
    )


def _written(done):
    return [
        pydicom.dcmread(path) for path in sorted(done.result.release.rglob("*.dcm"))
    ]


def _report(done):
    return json.loads(
        (done.result.release / run_report.RELEASE_REPORT).read_text(encoding="utf-8")
    )


def _secrets(key_file, store=None):
    """Return each form a project key or its custodian files can take."""
    key = keys.read_key_file(key_file)
    secrets = [
        key.secret,
        key.secret.hex().encode(),
        base64.b64encode(key.secret),
        key_file.read_bytes(),
        str(key_file).encode(),
    ]
    if store is not None:
        secrets.append(str(store).encode())
    return secrets


def _assert_discloses_none(data, secrets):
    for secret in secrets:
        assert secret not in data


def _transform(store=None, key=KEY):
    return InstanceTransform(
        compose_custom_policy([MODIFIED_DATES]),
        key,
        profiles=store,
        unvalidated_policy=True,
    )


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
def test_dates_move_by_the_offset_recorded_in_the_subjects_profile(tmp_path):
    # A subject keeps the offset of its first export, even where the key's
    # derivation would now give another.
    path = tmp_path / "custodian" / "profiles.json"
    path.parent.mkdir()
    store = profiles.ProfileStore.open(KEY, path)
    store.profile(SUBJECT)
    store.save()
    document = json.loads(path.read_text(encoding="utf-8"))
    (token,) = document["subjects"]
    derived = dates.date_offset_weeks(KEY, SUBJECT)
    stored = 53 if derived != 53 else 54
    document["subjects"][token] = {"date_offset_weeks": stored, "derivation": "older/0"}
    path.write_text(json.dumps(document), encoding="utf-8")

    (dataset,) = _slices(0)
    written = _transformed(_transform(profiles.ProfileStore.open(KEY, path)), dataset)

    assert written.StudyDate == _moved(_STUDY_DATE, stored)
    # Without the store, the key's derivation gives the offset.
    assert _transformed(_transform(), dataset).StudyDate == _moved(_STUDY_DATE, derived)


def test_a_transform_records_each_new_subject_in_its_store(tmp_path):
    store = profiles.ProfileStore.open(KEY, tmp_path / "profiles.json")
    transform = _transform(store)

    _transformed(transform, _slices(0)[0])

    assert transform.profiles is store
    store.save()
    document = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))
    assert len(document["subjects"]) == 1


def test_a_transform_refuses_a_store_of_another_key(tmp_path):
    store = profiles.ProfileStore.open(OTHER_KEY, tmp_path / "profiles.json")

    with pytest.raises(profiles.ProfileError, match="another key"):
        _transform(store)


def test_modify_dates_takes_the_offset_from_what_it_is_given():
    value = SourceValue(ElementPath((), "(0008,0020)"), "DA", _STUDY_DATE)

    written = modified_dates.modify_dates([value], KEY, SUBJECT, lambda _: 60)

    assert written[value.source] == ((_moved(_STUDY_DATE, 60),), False)


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
@pytest.mark.usefixtures("enabled")
def test_a_later_run_under_the_project_key_extends_the_earlier_one(tmp_path, custodian):
    first = _run(tmp_path, "first", _slices(0, 1), custodian)
    second = _run(tmp_path, "second", _slices(2), custodian)
    # A run-scoped key, for comparison.
    _write(tmp_path / "other" / "source", _slices(2))
    other = api.deidentify(
        tmp_path / "other" / "source",
        tmp_path / "other" / "release",
        qc_pack=tmp_path / "other" / "qc",
        options=[MODIFIED_DATES],
    )

    assert first.released and second.released and other.released
    earlier, later = _written(first), _written(second)
    assert len(earlier) == 2 and len(later) == 1
    for each in earlier:
        assert (each.PatientID, each.StudyInstanceUID, each.StudyDate) == (
            later[0].PatientID,
            later[0].StudyInstanceUID,
            later[0].StudyDate,
        )
    assert later[0].StudyDate != _STUDY_DATE
    (unrelated,) = _written(other)
    assert unrelated.PatientID != later[0].PatientID
    assert unrelated.StudyInstanceUID != later[0].StudyInstanceUID


@pytest.mark.usefixtures("enabled")
def test_the_store_is_saved_before_the_release_is_published(tmp_path, custodian):
    _, store = custodian

    done = _run(tmp_path, "first", _slices(0), custodian)

    assert done.released
    document = json.loads(store.read_text(encoding="utf-8"))
    assert len(document["subjects"]) == 1
    if os.name == "posix":
        assert stat.S_IMODE(store.stat().st_mode) == 0o600


@pytest.mark.usefixtures("enabled")
def test_a_store_that_cannot_be_saved_publishes_nothing(
    tmp_path, custodian, monkeypatch
):
    def fail(_store):
        raise OSError("disk full")

    monkeypatch.setattr(profiles.ProfileStore, "save", fail)

    with pytest.raises(profiles.ProfileError, match="nothing was published") as raised:
        _run(tmp_path, "first", _slices(0), custodian)

    assert str(tmp_path) not in str(raised.value)
    assert not (tmp_path / "first" / "release").exists()
    qc_pack = tmp_path / "first" / "qc"
    assert not qc_pack.exists() or not any(qc_pack.iterdir())


@pytest.mark.usefixtures("enabled")
def test_the_report_and_statement_say_the_key_is_a_project_key(tmp_path, custodian):
    key_file, store = custodian
    key = keys.read_key_file(key_file)

    done = _run(tmp_path, "first", _slices(0), custodian)

    assert _report(done)["key"] == {"scope": "project", "key_id": key.key_id}
    released = done.result.release
    statement = (released / run_report.CONFORMANCE_STATEMENT).read_text(
        encoding="utf-8"
    )
    assert "The run's key is a project key" in statement
    assert "Each run has its own" not in statement
    secrets = _secrets(key_file, store)
    for path in (*released.rglob("*"), *(tmp_path / "first" / "qc").rglob("*")):
        if path.is_file():
            _assert_discloses_none(path.read_bytes(), secrets)


@pytest.mark.usefixtures("enabled")
def test_a_run_scoped_key_is_reported_as_such(tmp_path):
    _write(tmp_path / "source", _slices(0))

    done = api.deidentify(
        tmp_path / "source", tmp_path / "release", qc_pack=tmp_path / "qc"
    )

    assert _report(done)["key"] == {"scope": "run", "key_id": None}


def _run_key(tmp_path, key_file, store):
    return command.run_key(
        key_file,
        store,
        source=tmp_path / "source",
        release=tmp_path / "release",
        qc_pack=tmp_path / "qc",
    )


def test_without_a_key_file_a_run_has_a_new_run_scoped_key(tmp_path):
    first, no_store = _run_key(tmp_path, None, None)
    second, _ = _run_key(tmp_path, None, None)

    assert no_store is None
    assert first != second


@pytest.mark.parametrize("given", ["key_file", "store"])
def test_a_key_file_and_store_are_given_together(tmp_path, custodian, given):
    key_file, store = custodian
    arguments = (key_file, None) if given == "key_file" else (None, store)

    with pytest.raises(command.TransformNotBuilt, match="together"):
        _run_key(tmp_path, *arguments)


def test_project_keys_are_refused_until_enabled(tmp_path, custodian):
    key_file, store = custodian

    with pytest.raises(command.TransformNotBuilt, match="not enabled"):
        _run_key(tmp_path, key_file, store)

    assert not store.exists()


@pytest.mark.usefixtures("enabled")
def test_an_enabled_project_key_is_read_with_its_store(tmp_path, custodian):
    key_file, store = custodian

    key, opened = _run_key(tmp_path, key_file, store)

    assert key == keys.read_key_file(key_file)
    assert opened is not None and opened.persistent
    assert opened.key_id == key.key_id


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize("place", ["source", "release", "qc"])
def test_a_key_file_inside_a_runs_directory_is_refused(tmp_path, custodian, place):
    _, store = custodian
    directory = tmp_path / place
    directory.mkdir()
    key_file = keys.write_key_file(directory / "key.json", KEY)

    with pytest.raises(command.TransformNotBuilt, match="key file") as raised:
        _run_key(tmp_path, key_file, store)

    assert str(tmp_path) not in str(raised.value)


@pytest.mark.usefixtures("enabled")
def test_a_store_inside_a_runs_directory_is_refused(tmp_path, custodian):
    key_file, _ = custodian
    (tmp_path / "qc").mkdir()

    with pytest.raises(command.TransformNotBuilt, match="profile store"):
        _run_key(tmp_path, key_file, tmp_path / "qc" / "profiles.json")


@pytest.mark.usefixtures("enabled")
def test_a_missing_or_unreadable_key_file_is_refused(tmp_path, custodian):
    key_file, store = custodian
    broken = key_file.parent / "broken.json"
    broken.write_text("{}", encoding="utf-8")

    for given in (key_file.parent / "missing.json", broken):
        with pytest.raises(command.TransformNotBuilt, match="key file") as raised:
            _run_key(tmp_path, given, store)
        assert str(tmp_path) not in str(raised.value)


@pytest.mark.usefixtures("enabled")
def test_a_store_of_another_key_is_refused(tmp_path, custodian):
    key_file, store = custodian
    other = profiles.ProfileStore.open(OTHER_KEY, store)
    other.save()

    with pytest.raises(command.TransformNotBuilt, match="profile store"):
        _run_key(tmp_path, key_file, store)


@pytest.mark.usefixtures("enabled")
def test_the_command_runs_under_a_project_key(tmp_path, custodian, capsys):
    key_file, store = custodian
    _write(tmp_path / "source", _slices(0))

    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--option",
            MODIFIED_DATES,
            "--key-file",
            str(key_file),
            "--profile-store",
            str(store),
        ]
    )

    assert status in (command.EXIT_RELEASED, command.EXIT_WITHHELD)
    assert store.is_file()
    report = json.loads(
        (tmp_path / "release" / run_report.RELEASE_REPORT).read_text(encoding="utf-8")
    )
    assert report["key"]["scope"] == "project"
    secrets = _secrets(key_file, store)
    printed = capsys.readouterr()
    _assert_discloses_none((printed.out + printed.err).encode(), secrets)
    for path in (*(tmp_path / "release").rglob("*"), *(tmp_path / "qc").rglob("*")):
        if path.is_file():
            _assert_discloses_none(path.read_bytes(), secrets)


def test_the_command_refuses_a_project_key_until_enabled(tmp_path, custodian, capsys):
    key_file, store = custodian
    _write(tmp_path / "source", _slices(0))

    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--key-file",
            str(key_file),
            "--profile-store",
            str(store),
        ]
    )

    assert status == command.EXIT_NOT_RUN
    printed = capsys.readouterr()
    assert "not enabled" in printed.err
    _assert_discloses_none(
        (printed.out + printed.err).encode(), _secrets(key_file, store)
    )
    assert not (tmp_path / "release").exists()
    assert not store.exists()


def test_the_statement_describes_each_key_scope():
    composed = compose_custom_policy([MODIFIED_DATES])
    run_scoped = conformance_markdown.render_markdown(
        conformance.conformance_statement(composed, vocabulary=None)
    )
    project = conformance_markdown.render_markdown(
        conformance.conformance_statement(composed, vocabulary=None, project_key=True)
    )

    assert "Each run has its own 256-bit key" in run_scoped
    assert "Across runs they are not consistent" in run_scoped
    assert "The run's key is a project key of 256 bits" in project
    assert "keeps its intervals to the earlier ones" in project
    assert "Releases under one key can therefore be linked" in project


def test_a_report_refuses_a_key_identifier_of_another_form():
    report = release_report.release_report(
        policy.compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        project_key="not an identifier",
    )

    with pytest.raises(release_report.ReleaseReportError, match="key"):
        release_report.report_document(report)


@posix_only
def test_the_key_command_writes_a_key_only_its_owner_can_read(tmp_path, capsys):
    path = tmp_path / "custodian" / "key.json"
    path.parent.mkdir()

    status = key_command.main([str(path)])

    assert status == key_command.EXIT_CREATED
    key = keys.read_key_file(path)
    printed = capsys.readouterr()
    assert printed.out.strip() == (
        f"wrote a new project key with identifier {key.key_id}"
    )
    _assert_discloses_none((printed.out + printed.err).encode(), _secrets(path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_key_command_never_replaces_a_key(tmp_path, capsys):
    path = tmp_path / "key.json"
    assert key_command.main([str(path)]) == key_command.EXIT_CREATED
    before = path.read_bytes()
    capsys.readouterr()

    assert key_command.main([str(path)]) == key_command.EXIT_NOT_CREATED

    assert path.read_bytes() == before
    error = capsys.readouterr().err
    assert "could not be created" in error
    assert str(path) not in error


def test_the_key_command_refuses_a_protected_directory(tmp_path, capsys):
    protected = tmp_path / "release"
    protected.mkdir()

    status = key_command.main(
        [str(protected / "key.json"), "--protect", str(protected)]
    )

    assert status == key_command.EXIT_NOT_CREATED
    assert not (protected / "key.json").exists()
    assert str(protected) not in capsys.readouterr().err
