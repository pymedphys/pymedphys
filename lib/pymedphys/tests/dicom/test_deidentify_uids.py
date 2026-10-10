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

"""Keyed replacement UIDs."""

import hashlib
import hmac
import uuid

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import keys, uid_registry, uids

st = hypothesis.strategies

# An invented key and UID, used only for known-answer tests.
FIXTURE_SECRET = bytes(range(32))
FIXTURE_UID = "1.2.840.99999.2.55.3.604688119.868.1234567890.1"

any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)
# UIDs as found, including invalid ones, which are replaced all the same.
any_uid = st.one_of(
    st.from_regex(uid_registry.UID_PATTERN, fullmatch=True),
    st.text(min_size=1),
).filter(lambda value: value.rstrip("\x00 "))
padding = st.text(alphabet="\x00 ", max_size=3)


def _frame(value):
    return len(value).to_bytes(4, "big") + value


def test_the_namespace_is_derived_from_its_documented_name():
    assert uids.UID_NAMESPACE == uuid.uuid5(
        uuid.NAMESPACE_URL, "https://docs.pymedphys.com/deidentify/uid-namespace"
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_a_replacement_follows_the_specified_derivation():
    # HMAC-SHA256 of the UID under the key, as the name of a version 5 UUID
    # in the PyMedPhys namespace, written under the 2.25 root.
    token = hmac.new(
        FIXTURE_SECRET,
        _frame(b"pymedphys-deid/1") + _frame(b"uid") + _frame(FIXTURE_UID.encode()),
        hashlib.sha256,
    ).digest()
    digest = hashlib.sha1(uids.UID_NAMESPACE.bytes + token).digest()
    expected = uuid.UUID(bytes=digest[:16], version=5)

    assert uids.replacement_uid(keys.DeidKey(FIXTURE_SECRET), FIXTURE_UID) == (
        f"2.25.{expected.int}"
    )


def test_replacements_are_pinned():
    # A changed derivation would silently break incremental exports.
    assert uids.replacement_uid(keys.DeidKey(FIXTURE_SECRET), FIXTURE_UID) == (
        "2.25.45880388381039869122547204841297202992"
    )


@hypothesis.given(st.uuids(), st.text())
def test_version_5_uuids_match_the_standard_library(namespace, name):
    # uuid.uuid5 accepts only text names before Python 3.12, and the token
    # is bytes, so the module builds the UUID itself.
    assert uids.uuid5(namespace, name.encode("utf-8")) == uuid.uuid5(namespace, name)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
@hypothesis.given(any_key, any_uid)
def test_a_replacement_is_a_valid_uid_from_a_version_5_uuid(key, uid):
    replacement = uids.replacement_uid(key, uid)

    assert uid_registry.is_uid(replacement)
    assert len(replacement) <= 44
    assert replacement.startswith("2.25.")
    derived = uuid.UUID(int=int(replacement.removeprefix("2.25.")))
    assert derived.version == 5
    assert derived.variant == uuid.RFC_4122


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
@hypothesis.given(any_key, any_uid, padding)
def test_a_replacement_depends_only_on_the_key_and_the_unpadded_uid(key, uid, pad):
    replacement = uids.replacement_uid(key, uid)

    assert uids.replacement_uid(keys.DeidKey(key.secret), uid + pad) == replacement


@hypothesis.given(
    st.lists(st.binary(min_size=32, max_size=32), min_size=2, max_size=2, unique=True),
    any_uid,
)
def test_different_keys_give_unrelated_replacements(secrets, uid):
    first, second = (keys.DeidKey(secret) for secret in secrets)

    assert uids.replacement_uid(first, uid) != uids.replacement_uid(second, uid)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
@hypothesis.given(
    any_key,
    st.lists(any_uid, min_size=2, max_size=2, unique_by=uids.normalise_uid),
)
def test_different_uids_give_different_replacements(key, pair):
    first, second = pair

    assert uids.replacement_uid(key, first) != uids.replacement_uid(key, second)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1.2.3", "1.2.3"),
        ("1.2.3\x00", "1.2.3"),
        ("1.2.3 ", "1.2.3"),
        ("1.2.3 \x00", "1.2.3"),
        (" 1.2.3", " 1.2.3"),
    ],
)
def test_only_trailing_padding_is_removed(value, expected):
    assert uids.normalise_uid(value) == expected


@pytest.mark.parametrize("value", ["", "\x00", "  "])
def test_an_empty_uid_has_no_replacement(value):
    with pytest.raises(ValueError, match="empty"):
        uids.replacement_uid(keys.DeidKey(FIXTURE_SECRET), value)
