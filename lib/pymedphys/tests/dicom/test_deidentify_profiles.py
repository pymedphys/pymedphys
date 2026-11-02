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

"""Subject profiles, the persisted per-subject values."""

import json
import os
import pathlib

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import dates, keys, profiles, pseudonyms

FIXTURE_KEY = keys.DeidKey(bytes(range(32)))
OTHER_KEY = keys.DeidKey(bytes(range(1, 33)))
SUBJECT = pseudonyms.SubjectIdentity.from_patient_id("MRN0001", "FIXTURE HOSPITAL")
OTHER_SUBJECT = pseudonyms.SubjectIdentity.from_patient_id(
    "MRN0002", "FIXTURE HOSPITAL"
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


def test_a_new_subject_gets_the_derived_offset():
    store = profiles.ProfileStore.ephemeral(FIXTURE_KEY)

    assert store.profile(SUBJECT) == profiles.SubjectProfile(
        date_offset_weeks=dates.date_offset_weeks(FIXTURE_KEY, SUBJECT),
        derivation="pymedphys-deid/1",
    )


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
def test_profiles_persist_across_runs(tmp_path):
    path = tmp_path / "custodian" / "profiles.json"
    path.parent.mkdir()
    first = profiles.ProfileStore.open(FIXTURE_KEY, path)
    profile = first.profile(SUBJECT)
    first.save()

    assert profiles.ProfileStore.open(FIXTURE_KEY, path).profile(SUBJECT) == profile


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
def test_a_stored_offset_wins_over_a_changed_derivation(tmp_path):
    # A change of derivation never silently changes an exported subject.
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.save()
    document = json.loads(path.read_text(encoding="utf-8"))
    (token,) = document["subjects"]
    stored = 53 if document["subjects"][token]["date_offset_weeks"] != 53 else 54
    document["subjects"][token] = {"date_offset_weeks": stored, "derivation": "older/0"}
    path.write_text(json.dumps(document), encoding="utf-8")

    assert profiles.ProfileStore.open(FIXTURE_KEY, path).profile(SUBJECT) == (
        profiles.SubjectProfile(date_offset_weeks=stored, derivation="older/0")
    )


def test_a_store_holds_no_identifiers_and_no_key(tmp_path):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.profile(OTHER_SUBJECT)
    store.save()
    text = path.read_text(encoding="utf-8")
    document = json.loads(text)

    assert "MRN000" not in text and "FIXTURE HOSPITAL" not in text
    assert FIXTURE_KEY.secret.hex() not in text
    assert document["format"] == "pymedphys-deid-profiles/1"
    assert document["key_id"] == FIXTURE_KEY.key_id
    assert set(document["subjects"]) == {
        FIXTURE_KEY.derive("subject", *identity.parts).hex()
        for identity in (SUBJECT, OTHER_SUBJECT)
    }


def test_a_store_belongs_to_one_key(tmp_path):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.save()

    with pytest.raises(profiles.ProfileError, match="another key"):
        profiles.ProfileStore.open(OTHER_KEY, path)


@posix_only
def test_a_store_is_readable_only_by_its_owner(tmp_path):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.save()

    assert path.stat().st_mode & 0o777 == 0o600


def test_saving_replaces_the_store_atomically(tmp_path):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.save()
    store.profile(OTHER_SUBJECT)
    store.save()

    assert len(json.loads(path.read_text(encoding="utf-8"))["subjects"]) == 2
    # No partial file is left beside the store.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "profiles.json"]


def test_saving_warns_where_permissions_are_not_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "_OWNER_ONLY_MODE_ENFORCED", False)
    store = profiles.ProfileStore.open(FIXTURE_KEY, tmp_path / "profiles.json")

    with pytest.warns(UserWarning, match="profile store"):
        store.save()


def test_a_store_is_not_kept_in_the_pymedphys_configuration(home):
    config = home / ".pymedphys"
    config.mkdir()

    with pytest.raises(profiles.ProfileError, match="configuration directory"):
        profiles.ProfileStore.open(FIXTURE_KEY, config / "profiles.json")


def test_a_store_is_not_kept_in_a_protected_directory(tmp_path):
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(profiles.ProfileError, match="protected directory"):
        profiles.ProfileStore.open(
            FIXTURE_KEY, output / "profiles.json", protected_dirs=[output]
        )


def test_an_ephemeral_store_cannot_be_saved(tmp_path):
    store = profiles.ProfileStore.ephemeral(FIXTURE_KEY)
    store.profile(SUBJECT)

    with pytest.raises(profiles.ProfileError, match="ephemeral"):
        store.save()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home"]


def test_profiles_are_isolated_per_key():
    first = profiles.ProfileStore.ephemeral(FIXTURE_KEY).profile(SUBJECT)
    second = profiles.ProfileStore.ephemeral(OTHER_KEY).profile(SUBJECT)

    assert first.date_offset_weeks == dates.date_offset_weeks(FIXTURE_KEY, SUBJECT)
    assert second.date_offset_weeks == dates.date_offset_weeks(OTHER_KEY, SUBJECT)


def _saved_document(tmp_path):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    store.profile(SUBJECT)
    store.save()
    return path, json.loads(path.read_text(encoding="utf-8"))


def _token(document):
    return next(iter(document["subjects"]))


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(format="pymedphys-deid-profiles/0"), "not a pymedphys"),
        (lambda d: d.pop("key_id"), "not a pymedphys"),
        (lambda d: d.update(subjects=[]), "subjects"),
        (
            lambda d: d["subjects"].update({"abc": d["subjects"][_token(d)]}),
            "subject token",
        ),
        (
            lambda d: d["subjects"][_token(d)].update(date_offset_weeks=0),
            "52 to 520",
        ),
        (
            lambda d: d["subjects"][_token(d)].update(date_offset_weeks=True),
            "52 to 520",
        ),
        (lambda d: d["subjects"][_token(d)].update(derivation=""), "derivation"),
        (lambda d: d["subjects"][_token(d)].update(extra=1), "fields"),
    ],
)
def test_a_malformed_store_is_rejected(tmp_path, change, message):
    path, document = _saved_document(tmp_path)
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(profiles.ProfileError, match=message):
        profiles.ProfileStore.open(FIXTURE_KEY, path)


BIRTH_DATE = profiles.BirthDate(
    "19790615",
    profiles.ReferenceStudy("2.25.123456789", "20190615", 40),
)


@pytest.mark.parametrize("birth_date", [BIRTH_DATE, profiles.NO_BIRTH_DATE])
def test_a_birth_date_persists_across_runs(tmp_path, birth_date):
    path = tmp_path / "profiles.json"
    store = profiles.ProfileStore.open(FIXTURE_KEY, path)
    recorded = store.record_birth_date(SUBJECT, birth_date)
    store.save()

    reopened = profiles.ProfileStore.open(FIXTURE_KEY, path)
    assert reopened.profile(SUBJECT) == recorded
    assert recorded.birth_date == birth_date
    assert recorded.date_offset_weeks == dates.date_offset_weeks(FIXTURE_KEY, SUBJECT)


def test_a_subject_without_a_birth_date_is_stored_without_one(tmp_path):
    _, document = _saved_document(tmp_path)

    assert "birth_date" not in document["subjects"][_token(document)]
    store = profiles.ProfileStore.open(FIXTURE_KEY, tmp_path / "profiles.json")
    assert store.profile(SUBJECT).birth_date is None


def test_a_recorded_birth_date_is_never_replaced():
    store = profiles.ProfileStore.ephemeral(FIXTURE_KEY)
    store.record_birth_date(SUBJECT, profiles.NO_BIRTH_DATE)

    with pytest.raises(profiles.ProfileError, match="already holds"):
        store.record_birth_date(SUBJECT, BIRTH_DATE)
    assert store.profile(SUBJECT).birth_date == profiles.NO_BIRTH_DATE
    # Other subjects are recorded apart.
    assert store.record_birth_date(OTHER_SUBJECT, BIRTH_DATE).birth_date == BIRTH_DATE


def test_a_birth_date_has_a_reference_exactly_when_it_has_a_value():
    with pytest.raises(ValueError, match="reference study"):
        profiles.BirthDate("19790615", None)
    with pytest.raises(ValueError, match="reference study"):
        profiles.BirthDate("", BIRTH_DATE.reference)


def _with_birth_date(document, **changes):
    stored = {
        "date": "19790615",
        "reference": {"study": "2.25.123456789", "date": "20190615", "age_years": 40},
    }
    for name, value in changes.items():
        if name in stored:
            stored[name] = value
        else:
            stored["reference"][name] = value
    document["subjects"][_token(document)]["birth_date"] = stored


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"date": "19790230"}, "not a date"),
        ({"date": ""}, "not a date"),
        ({"date": "1979615"}, "not a date"),
        ({"reference": None}, "without its reference"),
        ({"study": "1.2.3"}, "replacement UID"),
        ({"study": 2}, "replacement UID"),
        ({"date": "19790615", "age_years": -1}, "0 to 999"),
        ({"age_years": 1000}, "0 to 999"),
        ({"age_years": True}, "0 to 999"),
        ({"reference": {"study": "2.25.1", "date": "20190615"}}, "replacement UID"),
    ],
)
def test_a_malformed_birth_date_is_rejected(tmp_path, changes, message):
    path, document = _saved_document(tmp_path)
    _with_birth_date(document, **changes)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(profiles.ProfileError, match=message):
        profiles.ProfileStore.open(FIXTURE_KEY, path)


def test_a_birth_date_without_its_fields_is_rejected(tmp_path):
    path, document = _saved_document(tmp_path)
    document["subjects"][_token(document)]["birth_date"] = {"date": ""}
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(profiles.ProfileError, match="date and reference"):
        profiles.ProfileStore.open(FIXTURE_KEY, path)


def test_an_unreadable_store_is_rejected(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(profiles.ProfileError, match="could not be read"):
        profiles.ProfileStore.open(FIXTURE_KEY, path)
