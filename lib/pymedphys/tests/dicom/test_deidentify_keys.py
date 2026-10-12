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

"""De-identification keys and their derivations."""

import base64
import hashlib
import hmac
import json
import os
import pathlib
import pickle
import re

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import keys

st = hypothesis.strategies

# An invented key, used only for known-answer tests.
FIXTURE_SECRET = bytes(range(32))

any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)
parts = st.lists(st.one_of(st.text(), st.binary()), max_size=4)

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX file modes and symbolic links"
)


def _frame(value):
    return len(value).to_bytes(4, "big") + value


def test_generated_keys_are_256_bits_and_distinct():
    first, second = keys.DeidKey.generate(), keys.DeidKey.generate()

    assert len(first.secret) == 32
    assert first != second


@pytest.mark.parametrize("secret", [b"", bytes(31), bytes(33), "0" * 32, None])
def test_a_key_must_be_32_bytes(secret):
    with pytest.raises(keys.DeidKeyError, match="32 bytes"):
        keys.DeidKey(secret)


def test_derive_follows_the_specified_framing():
    key = keys.DeidKey(FIXTURE_SECRET)
    message = (
        _frame(b"pymedphys-deid/1")
        + _frame(b"uid")
        + _frame(b"1.2.3")
        + _frame(b"\x00")
    )

    assert (
        key.derive("uid", "1.2.3", b"\x00")
        == hmac.new(FIXTURE_SECRET, message, hashlib.sha256).digest()
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_derivations_are_pinned():
    # A changed derivation would silently change every exported value, so
    # these known answers change only with a new derivation version.
    key = keys.DeidKey(FIXTURE_SECRET)

    assert key.derive("uid", "1.2.3").hex() == (
        "c45e489ac8fb88a9394e0988d90a22b010cf33072f7170b8e1eef9cca3378fae"
    )
    assert key.key_id == "536c8d66a475c06b64b8abaa93e60568"


@hypothesis.given(
    any_key,
    st.lists(
        st.lists(st.text(), min_size=1, max_size=4),
        min_size=2,
        max_size=2,
        unique_by=tuple,
    ),
)
def test_parts_are_framed_so_different_splits_differ(key, pair):
    first, second = pair

    assert key.derive("uid", *first) != key.derive("uid", *second)


@hypothesis.given(any_key, parts)
def test_domains_are_separated(key, values):
    assert key.derive("uid", *values) != key.derive("key-id", *values)


def test_an_unregistered_domain_is_rejected():
    with pytest.raises(ValueError, match="domain"):
        keys.DeidKey(FIXTURE_SECRET).derive("uids", "1.2.3")


@hypothesis.given(any_key)
def test_the_key_id_is_stable_hex_and_reveals_nothing_else(key):
    assert key.key_id == keys.DeidKey(key.secret).key_id
    assert re.fullmatch("[0-9a-f]{32}", key.key_id)
    assert key.secret.hex() not in repr(key)
    assert repr(key) == f"DeidKey(key_id={key.key_id!r})"


@hypothesis.given(any_key, any_key)
def test_keys_compare_by_secret(first, second):
    assert (first == second) == (first.secret == second.secret)
    assert first == keys.DeidKey(first.secret)
    assert hash(first) == hash(keys.DeidKey(first.secret))


def test_keys_can_be_sent_to_worker_processes():
    key = keys.DeidKey(FIXTURE_SECRET)

    assert pickle.loads(pickle.dumps(key)) == key


@pytest.fixture(name="home")
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.mark.usefixtures("home")
def test_a_key_file_round_trips(tmp_path):
    key = keys.DeidKey.generate()
    path = tmp_path / "project.key"

    assert keys.write_key_file(path, key) == path.resolve()
    assert keys.read_key_file(path) == key


@pytest.mark.usefixtures("home")
def test_a_key_file_records_its_format_and_identifier(tmp_path):
    key = keys.DeidKey(FIXTURE_SECRET)
    path = keys.write_key_file(tmp_path / "project.key", key)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": "pymedphys-deid-key/1",
        "key_id": key.key_id,
        "key": base64.b64encode(FIXTURE_SECRET).decode("ascii"),
    }


@posix_only
@pytest.mark.usefixtures("home")
def test_a_key_file_is_readable_only_by_its_owner(tmp_path):
    path = keys.write_key_file(tmp_path / "project.key", keys.DeidKey.generate())

    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.usefixtures("home")
def test_a_key_file_is_never_overwritten(tmp_path):
    path = tmp_path / "project.key"
    path.write_text("existing", encoding="utf-8")

    with pytest.raises(keys.DeidKeyError, match="already exists"):
        keys.write_key_file(path, keys.DeidKey.generate())
    assert path.read_text(encoding="utf-8") == "existing"


@posix_only
@pytest.mark.usefixtures("home")
def test_a_key_file_is_not_written_through_a_symbolic_link(tmp_path):
    target = tmp_path / "elsewhere.key"
    link = tmp_path / "project.key"
    link.symlink_to(target)

    with pytest.raises(keys.DeidKeyError, match="already exists"):
        keys.write_key_file(link, keys.DeidKey.generate())
    assert not target.exists()


def test_a_key_file_is_not_written_in_the_pymedphys_configuration(home):
    config = home / ".pymedphys"
    config.mkdir()

    with pytest.raises(keys.DeidKeyError, match="configuration directory"):
        keys.write_key_file(config / "project.key", keys.DeidKey.generate())
    assert not (config / "project.key").exists()


def test_writing_a_key_file_does_not_create_the_configuration_directory(tmp_path, home):
    keys.write_key_file(tmp_path / "project.key", keys.DeidKey.generate())

    assert not (home / ".pymedphys").exists()


@pytest.mark.usefixtures("home")
def test_a_key_file_is_not_written_in_a_protected_directory(tmp_path):
    output = tmp_path / "output"
    (output / "series").mkdir(parents=True)

    with pytest.raises(keys.DeidKeyError, match="protected directory"):
        keys.write_key_file(
            output / "series" / "project.key",
            keys.DeidKey.generate(),
            protected_dirs=[output],
        )
    assert not (output / "series" / "project.key").exists()


@pytest.mark.usefixtures("home")
def test_writing_a_key_file_warns_where_permissions_are_not_enforced(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(keys, "_OWNER_ONLY_MODE_ENFORCED", False)

    with pytest.warns(UserWarning, match="access"):
        keys.write_key_file(tmp_path / "project.key", keys.DeidKey.generate())


def _key_document(**changes):
    document = {
        "format": "pymedphys-deid-key/1",
        "key_id": keys.DeidKey(FIXTURE_SECRET).key_id,
        "key": base64.b64encode(FIXTURE_SECRET).decode("ascii"),
    }
    document.update(changes)
    return document


@pytest.mark.parametrize(
    "document, message",
    [
        (_key_document(format="pymedphys-deid-key/0"), "not a pymedphys-deid-key/1"),
        (_key_document(extra=1), "not a pymedphys-deid-key/1"),
        (_key_document(key="not base64!"), "32-byte key"),
        (_key_document(key=base64.b64encode(bytes(31)).decode("ascii")), "32-byte key"),
        (_key_document(key_id="0" * 32), "does not match"),
        (_key_document(key_id="\u00e9"), "does not match"),
        (_key_document(key_id=None), "does not match"),
        (_key_document(key_id=[]), "does not match"),
        (_key_document(key_id=1), "does not match"),
        ([], "not a pymedphys-deid-key/1"),
    ],
)
def test_a_malformed_key_file_is_rejected(tmp_path, document, message):
    path = tmp_path / "project.key"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(keys.DeidKeyError, match=message) as raised:
        keys.read_key_file(path)
    assert base64.b64encode(FIXTURE_SECRET).decode("ascii") not in str(raised.value)
    assert FIXTURE_SECRET.hex() not in str(raised.value)


def test_an_unreadable_key_file_is_rejected(tmp_path):
    path = tmp_path / "project.key"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(keys.DeidKeyError, match="could not be read"):
        keys.read_key_file(path)
