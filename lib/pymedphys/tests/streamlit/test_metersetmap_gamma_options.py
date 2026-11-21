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

"""How the MetersetMap app reads the ``[gamma]`` table of its configuration.

Configuration files written before version 0.42.0, and the demo data, name
the gamma options as ``pymedphys.gamma`` named them then. The app must keep
reading those files, and must also read the current option names.
"""

import inspect
import pathlib
import tomllib

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

pytest.importorskip("streamlit")

# pylint: disable = wrong-import-position
from pymedphys._streamlit.apps.metersetmap import _config  # noqa: E402

GAMMA_OPTION_NAMES = set(inspect.signature(pymedphys.gamma).parameters)


def test_option_names_from_before_version_0_42_are_translated():
    # The [gamma] table of the demo data's configuration.
    table = {
        "dose_percent_threshold": 2,
        "distance_mm_threshold": 0.5,
        "local_gamma": True,
        "quiet": True,
        "max_gamma": 5,
        "lower_percent_dose_cutoff": 20,
    }

    assert _config.gamma_options_from_table(table) == {
        "dose_criterion_percent": 2,
        "distance_criterion_mm": 0.5,
        "normalisation": "local",
        "gamma_cap": 5,
        "lower_dose_cutoff_percent": 20,
    }


def test_every_earlier_option_becomes_an_option_of_gamma():
    table = {
        "dose_percent_threshold": 3,
        "distance_mm_threshold": 2,
        "lower_percent_dose_cutoff": 10,
        "interp_fraction": 20,
        "max_gamma": 2,
        "local_gamma": False,
        "global_normalisation": 1.5,
        "skip_once_passed": True,
        "random_subset": 100,
        "ram_available": 2**20,
        "quiet": False,
        "interp_algo": "scipy",
    }

    options = _config.gamma_options_from_table(table)

    assert set(options) <= GAMMA_OPTION_NAMES
    assert options["normalisation"] == "global"
    assert options["search_step_fraction"] == 1 / 20
    assert options["normalisation_dose"] == 1.5
    assert options["interpolator"] == "scipy"
    assert options["memory_budget_bytes"] == 2**20
    assert "quiet" not in options
    # Options that kept their names are passed through.
    assert options["skip_once_passed"] is True
    assert options["random_subset"] == 100


def test_the_bundled_configuration_uses_the_current_option_names():
    path = pathlib.Path(_config.HERE, "config.toml")
    table = tomllib.loads(path.read_text(encoding="utf-8"))["gamma"]

    assert _config.gamma_options_from_table(table) == table
    assert set(table) <= GAMMA_OPTION_NAMES


def test_translated_options_are_accepted_by_gamma():
    table = {
        "dose_percent_threshold": 2,
        "distance_mm_threshold": 0.5,
        "local_gamma": True,
        "quiet": True,
        "max_gamma": 5,
        "lower_percent_dose_cutoff": 20,
    }
    axis = np.array([0.0, 1.0, 2.0])
    dose = np.ones(3)

    result = pymedphys.gamma(
        axis, dose, axis, dose, **_config.gamma_options_from_table(table)
    )

    assert (result.passed, result.analysed) == (3, 3)
    assert result.settings.normalisation == "local"
    assert result.settings.gamma_cap == 5


def test_an_option_set_under_both_of_its_names_is_rejected():
    with pytest.raises(ValueError, match="gamma_cap twice"):
        _config.gamma_options_from_table({"max_gamma": 5, "gamma_cap": 2})
