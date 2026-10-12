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

"""Keyed patient pseudonyms."""

import base64
import hashlib
import hmac
import re

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import keys, pseudonyms

st = hypothesis.strategies

# An invented key and identifiers, used only for known-answer tests.
FIXTURE_SECRET = bytes(range(32))
FIXTURE_KEY = keys.DeidKey(FIXTURE_SECRET)

any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)
# Patient IDs as found: LO text, possibly padded, never only spaces.
any_identifier = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"), blacklist_characters="\\"
    ),
    min_size=1,
    max_size=64,
).filter(str.strip)
any_identity = st.one_of(
    st.builds(
        pseudonyms.SubjectIdentity.from_patient_id, any_identifier, any_identifier
    ),
    st.builds(pseudonyms.SubjectIdentity.from_patient_id, any_identifier),
    st.builds(pseudonyms.SubjectIdentity.curated, any_identifier),
)


def _frame(value):
    return len(value).to_bytes(4, "big") + value


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_a_pseudonym_follows_the_specified_derivation():
    identity = pseudonyms.SubjectIdentity.from_patient_id("MRN0001", "FIXTURE HOSPITAL")
    token = hmac.new(
        FIXTURE_SECRET,
        _frame(b"pymedphys-deid/1")
        + _frame(b"patient")
        + _frame(b"patient-id")
        + _frame(b"FIXTURE HOSPITAL")
        + _frame(b"MRN0001"),
        hashlib.sha256,
    ).digest()
    code = base64.b32encode(token[:10]).decode("ascii")

    assert pseudonyms.patient_pseudonym(FIXTURE_KEY, identity) == (
        pseudonyms.PatientPseudonym(
            patient_id=f"DEID-{code}", patients_name=f"DEIDENTIFIED^{code}"
        )
    )


def test_pseudonyms_are_pinned():
    identity = pseudonyms.SubjectIdentity.from_patient_id("MRN0001", "FIXTURE HOSPITAL")

    assert pseudonyms.patient_pseudonym(FIXTURE_KEY, identity).patient_id == (
        "DEID-3IG6TYZOJUCGHKBY"
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@hypothesis.given(any_key, any_identity)
def test_a_pseudonym_is_valid_for_its_vr_and_conspicuous(key, identity):
    from pydicom import config, valuerep

    pseudonym = pseudonyms.patient_pseudonym(key, identity)

    valuerep.validate_value("LO", pseudonym.patient_id, config.RAISE)
    valuerep.validate_value("PN", pseudonym.patients_name, config.RAISE)
    assert re.fullmatch("DEID-[A-Z2-7]{16}", pseudonym.patient_id)
    assert re.fullmatch("DEIDENTIFIED\\^[A-Z2-7]{16}", pseudonym.patients_name)
    assert pseudonym.patient_id[5:] == pseudonym.patients_name[13:]


@hypothesis.given(any_key, any_identity)
def test_a_pseudonym_depends_only_on_the_key_and_the_identity(key, identity):
    assert pseudonyms.patient_pseudonym(
        keys.DeidKey(key.secret), identity
    ) == pseudonyms.patient_pseudonym(key, identity)


@hypothesis.given(
    st.lists(st.binary(min_size=32, max_size=32), min_size=2, max_size=2, unique=True),
    any_identity,
)
def test_different_keys_give_unrelated_pseudonyms(secrets, identity):
    first, second = (keys.DeidKey(secret) for secret in secrets)

    assert pseudonyms.patient_pseudonym(first, identity) != (
        pseudonyms.patient_pseudonym(second, identity)
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@hypothesis.given(any_key, st.lists(any_identity, min_size=2, max_size=2, unique=True))
def test_different_subjects_give_different_pseudonyms(key, pair):
    first, second = pair

    assert pseudonyms.patient_pseudonym(key, first) != (
        pseudonyms.patient_pseudonym(key, second)
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_the_same_identifier_from_another_issuer_is_another_subject():
    first = pseudonyms.SubjectIdentity.from_patient_id("123456", "HOSPITAL A")
    second = pseudonyms.SubjectIdentity.from_patient_id("123456", "HOSPITAL B")
    unissued = pseudonyms.SubjectIdentity.from_patient_id("123456")
    curated = pseudonyms.SubjectIdentity.curated("123456")

    assert (
        len(
            {
                pseudonyms.patient_pseudonym(FIXTURE_KEY, identity)
                for identity in (first, second, unissued, curated)
            }
        )
        == 4
    )


def test_padding_is_not_part_of_an_identity():
    # LO values may be padded with leading and trailing spaces (PS3.5 6.2).
    assert pseudonyms.SubjectIdentity.from_patient_id(" 123456 ", "HOSPITAL A ") == (
        pseudonyms.SubjectIdentity.from_patient_id("123456", "HOSPITAL A")
    )


@pytest.mark.parametrize("identifier", ["", "   ", "\x00"])
def test_an_empty_identity_cannot_name_a_subject(identifier):
    with pytest.raises(ValueError, match="empty"):
        pseudonyms.SubjectIdentity.from_patient_id(identifier)
    with pytest.raises(ValueError, match="empty"):
        pseudonyms.SubjectIdentity.curated(identifier)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_a_pseudonym_does_not_contain_the_identifier():
    for identifier in ("MRN0001", "RT-2026-0042", "Q7XK2PLM"):
        pseudonym = pseudonyms.patient_pseudonym(
            FIXTURE_KEY, pseudonyms.SubjectIdentity.from_patient_id(identifier)
        )

        assert identifier not in pseudonym.patient_id + pseudonym.patients_name


def test_a_key_enumerates_low_entropy_identifiers():
    # Why a project key is as sensitive as a crosswalk: whoever holds it can
    # try every plausible medical record number.
    secret = pseudonyms.patient_pseudonym(
        FIXTURE_KEY, pseudonyms.SubjectIdentity.from_patient_id("004217")
    )

    found = [
        candidate
        for candidate in (f"{number:06d}" for number in range(10_000))
        if pseudonyms.patient_pseudonym(
            FIXTURE_KEY, pseudonyms.SubjectIdentity.from_patient_id(candidate)
        )
        == secret
    ]

    assert found == ["004217"]


def test_an_identity_does_not_show_its_identifier():
    identity = pseudonyms.SubjectIdentity.from_patient_id("MRN0001", "FIXTURE HOSPITAL")

    assert "MRN0001" not in repr(identity)
    assert "FIXTURE HOSPITAL" not in repr(identity)
