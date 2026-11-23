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

"""How the MetersetMap app uses the ``[gamma]`` table of its configuration.

The app passes the table to ``pymedphys.gamma`` as written, so the table
takes that function's option names.
"""

import inspect
import pathlib
import tomllib

from pymedphys._imports import pytest

import pymedphys

pytest.importorskip("streamlit")

# pylint: disable = wrong-import-position
from pymedphys._streamlit.apps.metersetmap import _config  # noqa: E402

GAMMA_OPTION_NAMES = set(inspect.signature(pymedphys.gamma).parameters)


def test_the_gamma_table_is_passed_on_as_written():
    table = {
        "dose_criterion_percent": 3,
        "distance_criterion_mm": 2,
        "normalisation": "global",
        "random_subset": 100,
    }

    options = _config.get_gamma_options({"gamma": table}, advanced_mode=False)

    assert options == table


def test_the_bundled_configuration_uses_the_option_names_of_gamma():
    path = pathlib.Path(_config.HERE, "config.toml")
    table = tomllib.loads(path.read_text(encoding="utf-8"))["gamma"]

    assert set(table) <= GAMMA_OPTION_NAMES
