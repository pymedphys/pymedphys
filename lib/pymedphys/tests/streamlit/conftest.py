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

"""Fixtures for the Streamlit GUI tests."""

# pylint: disable = redefined-outer-name

import pathlib
from typing import Iterator

import pytest

from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys import _config as pmp_config

from . import apptest_utilities as utl


@pytest.fixture(scope="session", autouse=True)
def headless_matplotlib() -> None:
    """Draw with the non-interactive Agg backend.

    ``AppTest`` runs the apps on a worker thread, and matplotlib's GUI
    backends abort the interpreter when a figure is created off the main
    thread. ``streamlit run`` forces Agg itself; the test harness does not,
    and the ``MPLBACKEND`` default set in the root conftest only helps when
    matplotlib has not already been imported with another backend.
    """
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")


@pytest.fixture(scope="session")
def demo_directory(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Extract the GUI demo data once per session.

    The metersetmap and electrons apps extract the same archive into the
    current working directory, so the tests run from ``demo_directory.parent``.
    """
    working_directory = tmp_path_factory.mktemp("streamlit-demo")
    pymedphys.zip_data_paths(utl.DEMO_DATA_ZIP, extract_directory=working_directory)

    return working_directory.joinpath(utl.DEMO_DIRECTORY_NAME)


@pytest.fixture
def demo_working_directory(
    demo_directory: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    monkeypatch.chdir(demo_directory.parent)

    return demo_directory


# The gamma options of the demo comparison, under the names that
# pymedphys.gamma gives them.
DEMO_GAMMA_TABLE = {
    "dose_criterion_percent": 2,
    "distance_criterion_mm": 0.5,
    "normalisation": "local",
    "gamma_cap": 5,
    "lower_dose_cutoff_percent": 20,
}


@pytest.fixture
def demo_gamma_table(
    demo_directory: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict]:
    """Give the demo configuration a ``[gamma]`` table that gamma accepts.

    The MetersetMap app passes the ``[gamma]`` table of its configuration to
    ``pymedphys.gamma`` as written. The demo archive was published before
    version 0.42.0 renamed that function's options, so its table is no longer
    one that gamma accepts. Until the archive is republished, a test that
    reaches gamma takes the table from here: the same criteria, under the
    current names.

    The caches are cleared on the way in and on the way out, for the reason
    given in ``demo_config_on_disk``.
    """
    original_get_config = pmp_config.get_config

    def get_config(path=None):
        config = original_get_config(path=path)
        if (
            path is not None
            and pathlib.Path(path).resolve() == demo_directory.resolve()
        ):
            config["gamma"] = dict(DEMO_GAMMA_TABLE)

        return config

    st.cache_data.clear()
    monkeypatch.setattr(pmp_config, "get_config", get_config)

    yield dict(DEMO_GAMMA_TABLE)

    st.cache_data.clear()


@pytest.fixture
def demo_config_on_disk(
    demo_directory: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pathlib.Path]:
    """Serve the demo configuration to apps that read the user's config.toml.

    The apps memoise ``get_config`` with ``st.cache_data`` for the life of the
    process, and an earlier test may already have cached another file (the
    pseudonymisation strategy writes a minimal ``~/.pymedphys/config.toml``
    into the session's temporary home directory), so the caches are cleared
    on the way in and again on the way out.
    """
    original_get_config = pmp_config.get_config

    def get_config(path=None):
        return original_get_config(path=demo_directory if path is None else path)

    st.cache_data.clear()
    monkeypatch.setattr(pmp_config, "get_config", get_config)

    yield demo_directory

    st.cache_data.clear()
