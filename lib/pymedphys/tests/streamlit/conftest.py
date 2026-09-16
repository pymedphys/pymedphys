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

import pytest

import pymedphys
from pymedphys import _config as pmp_config

from . import apptest_utilities as utl


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


@pytest.fixture
def demo_config_on_disk(
    demo_directory: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    """Serve the demo configuration to apps that read the user's config.toml."""
    original_get_config = pmp_config.get_config

    def get_config(path=None):
        return original_get_config(path=demo_directory if path is None else path)

    monkeypatch.setattr(pmp_config, "get_config", get_config)

    return demo_directory
