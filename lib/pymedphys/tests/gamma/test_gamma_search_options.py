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

"""The shell search names its options as ``pymedphys.gamma`` does.

:mod:`pymedphys._gamma.implementation.shell` is private. Its options have
the names and the meanings of the public function's, so nothing is
translated between the two.
"""

import inspect

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._gamma.implementation import shell
from pymedphys._utilities import createshells

Options = shell.GammaInternalFixedOptions


def _profile():
    axis = np.array([0.0, 1.0, 2.0])
    dose = np.array([1.0, 2.0, 4.0])

    return axis, dose, axis, dose


def test_the_search_takes_no_option_under_a_name_of_its_own():
    public = set(inspect.signature(pymedphys.gamma).parameters)
    search = set(inspect.signature(Options.from_user_inputs).parameters)

    # What to do when the 'pymedphys' interpolator cannot use the evaluation
    # axes is the one choice that pymedphys.gamma makes for its callers.
    assert search - public == {"uneven_axes"}


def test_the_search_holds_its_options_under_their_public_names():
    options = Options.from_user_inputs(
        *_profile(),
        [3, 2],
        1.5,
        search_step_fraction=0.25,
        gamma_cap=2,
        normalisation="local",
        normalisation_dose=8,
        memory_budget_bytes=1000,
        interpolator="scipy",
    )

    np.testing.assert_array_equal(options.dose_criterion_percent, [3, 2])
    np.testing.assert_array_equal(options.distance_criterion_mm, [1.5])
    assert options.search_step_fraction == 0.25
    assert options.gamma_cap == 2
    assert options.normalisation == "local"
    assert options.normalisation_dose == 8
    assert options.memory_budget_bytes == 1000
    assert options.interpolator == "scipy"


def test_the_search_fills_in_the_defaults_of_gamma():
    options = Options.from_user_inputs(*_profile(), 3, 3)

    assert options.search_step_fraction == shell.DEFAULT_SEARCH_STEP_FRACTION
    assert options.gamma_cap == np.inf
    assert options.normalisation == "global"
    assert options.normalisation_dose == 4
    assert options.lower_dose_cutoff == 0.8
    assert options.memory_budget_bytes == shell.DEFAULT_MEMORY_BUDGET_BYTES
    assert options.interpolator == "pymedphys"


@pytest.mark.parametrize("normalisation", ["Local", "relative", "", True, False, None])
def test_the_search_rejects_a_normalisation_it_does_not_know(normalisation):
    # Normalisation was once a boolean. Anything but the two names must be
    # refused, because the search would otherwise treat it as global.
    with pytest.raises(ValueError, match='normalisation must be "global" or "local"'):
        Options.from_user_inputs(*_profile(), 3, 3, normalisation=normalisation)


@pytest.mark.parametrize(
    ("distance_criterion_mm", "search_step_fraction"),
    [(3, 0.1), (0.7, 0.1), (3, 0.05), (1.5, 0.2), (2, 0.3)],
)
def test_the_search_step_is_the_fraction_of_the_distance_criterion(
    distance_criterion_mm, search_step_fraction, monkeypatch
):
    recorded = []
    original = createshells.calculate_coordinates_shell

    def record(distance, num_dimensions, distance_step_size):
        recorded.append(float(distance_step_size))
        return original(distance, num_dimensions, distance_step_size)

    monkeypatch.setattr(createshells, "calculate_coordinates_shell", record)
    axis = np.arange(0.0, 10.0)

    pymedphys.gamma(
        axis,
        np.ones(10),
        axis,
        np.full(10, 1.5),
        3,
        distance_criterion_mm,
        search_step_fraction=search_step_fraction,
    )

    assert len(recorded) > 1
    assert set(recorded) == {distance_criterion_mm * search_step_fraction}
