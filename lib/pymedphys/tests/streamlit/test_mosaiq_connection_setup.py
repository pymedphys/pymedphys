# Copyright (C) 2026 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Entering Mosaiq connection details when no site is configured.

The credential store and the database are replaced with in-memory fakes,
so these tests cover the setup flow and the config it saves, not live
Mosaiq connectivity.
"""

# pylint: disable = redefined-outer-name, import-outside-toplevel

import pathlib
from typing import Dict, Iterator, Tuple

from pymedphys._imports import pytest
from pymedphys._imports import toml

from pymedphys import _config as pmp_config

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

HOSTNAME = "mosaiq.example.test"


def _connection_app():
    import streamlit as st

    from pymedphys._streamlit.utilities import mosaiq as st_mosaiq

    connection = st_mosaiq.get_mosaiq_connection_with_prompts()
    st.write(f"Connected: `{connection}`")
    st.text_input("Patient ID")


@pytest.fixture
def config_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pathlib.Path]:
    from pymedphys._imports import streamlit as st

    directory = tmp_path / ".pymedphys"
    directory.mkdir()
    monkeypatch.setattr(pmp_config, "config_dir_path", lambda: directory)

    st.cache_data.clear()
    st.cache_resource.clear()
    yield directory
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def credential_store(monkeypatch: pytest.MonkeyPatch) -> Dict[Tuple, Dict[str, str]]:
    """Stand in for the keyring and accept any stored username and password."""
    from pymedphys._mosaiq import connect as _connect
    from pymedphys._mosaiq import credentials as _credentials

    store: Dict[Tuple, Dict[str, str]] = {}

    def get_username_and_password(hostname, port, database):
        entry = store.get((hostname, port, database), {})
        return entry.get("username"), entry.get("password")

    def save(field):
        def save_field(value, hostname, port, database):
            store.setdefault((hostname, port, database), {})[field] = value

        return save_field

    def connect_with_credentials(username, _password, hostname, port, database):
        return f"{username}@{hostname}:{port}/{database}"

    monkeypatch.setattr(
        _credentials,
        "get_username_and_password_without_prompt_fallback",
        get_username_and_password,
    )
    monkeypatch.setattr(_credentials, "save_username", save("username"))
    monkeypatch.setattr(_credentials, "save_password", save("password"))
    monkeypatch.setattr(_connect, "connect_with_credentials", connect_with_credentials)

    return store


def _start():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_function(
        _connection_app, default_timeout=utl.INDEX_TIMEOUT_SECONDS
    ).run()


def _submit(app_test, *, save: bool, hostname: str = HOSTNAME):
    utl.widget(app_test.text_input, "SQL Server Hostname").input(hostname).run()
    utl.widget(app_test.checkbox, "Save connection details to config file").set_value(
        save
    ).run()
    app_test.button(key="mosaiq_prompt_connect").click().run()
    utl.assert_no_exception(app_test)


def _connected(app_test):
    return utl.code_values(app_test, "Connected")


def _labels(elements):
    return [element.label for element in elements]


@pytest.mark.usefixtures("credential_store")
def test_unsaved_connection_survives_credential_and_patient_entry(config_dir):
    app_test = _start()
    _submit(app_test, save=False)

    username = [w for w in app_test.text_input if w.label.startswith("Username")]
    assert len(username) == 1
    username[0].input("physicist").run()
    utl.widget(app_test.text_input, "Password").input("secret").run()
    [login] = [b for b in app_test.button if b.key != "mosaiq_prompt_connect"]
    login.click().run()
    utl.assert_no_exception(app_test)

    expected = f"physicist@{HOSTNAME}:1433/MOSAIQ"
    assert _connected(app_test) == [expected]

    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    utl.assert_no_exception(app_test)

    assert _connected(app_test) == [expected]
    assert utl.widget(app_test.text_input, "Patient ID").value == "989898"
    assert not (config_dir / "config.toml").exists()


@pytest.mark.usefixtures("config_dir")
def test_changing_a_submitted_setting_needs_another_connect(credential_store):
    credential_store[(HOSTNAME, 1433, "MOSAIQ")] = {
        "username": "physicist",
        "password": "secret",
    }
    app_test = _start()
    _submit(app_test, save=False)
    assert len(_connected(app_test)) == 1

    utl.widget(app_test.text_input, "SQL Server Hostname").input(
        "other.example.test"
    ).run()
    utl.assert_no_exception(app_test)

    assert _connected(app_test) == []
    assert "Patient ID" not in _labels(app_test.text_input)


def test_saved_site_replaces_the_setup_form(config_dir, credential_store):
    """A config that loads but has no Mosaiq site is cached before saving."""
    (config_dir / "config.toml").write_text("version = 0\n", encoding="utf-8")
    credential_store[(HOSTNAME, 1433, "MOSAIQ")] = {
        "username": "physicist",
        "password": "secret",
    }
    app_test = _start()
    _submit(app_test, save=True)

    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    utl.assert_no_exception(app_test)

    assert "SQL Server Hostname" not in _labels(app_test.text_input)
    assert utl.widget(app_test.text_input, "Patient ID").value == "989898"
    assert len(_connected(app_test)) == 1


@pytest.mark.parametrize("hops", [1, 2])
def test_saving_writes_to_the_file_config_is_read_from(config_dir, hops):
    from pymedphys._streamlit.utilities import mosaiq as st_mosaiq

    target = config_dir / "shared" / "config.toml"
    target.parent.mkdir()
    target.write_text("version = 0\n", encoding="utf-8")

    source = target
    for hop in range(hops - 1):
        source = config_dir / f"hop{hop}.toml"
        source.write_text(f"redirect = '{target}'\n", encoding="utf-8")
    root = config_dir / "config.toml"
    root.write_text(f"redirect = '{source}'\n", encoding="utf-8")

    saved_to = st_mosaiq.save_mosaiq_config_to_file("clinic", HOSTNAME)

    assert saved_to == target
    assert toml.loads(root.read_text(encoding="utf-8")) == {"redirect": str(source)}
    [site] = pmp_config.get_config()["site"]
    assert site["name"] == "clinic"
    assert site["mosaiq"]["hostname"] == HOSTNAME
