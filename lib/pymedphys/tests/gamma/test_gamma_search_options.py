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


def _samples(shell_points, point):
    x, y = shell_points
    return np.any(np.hypot(x - point[0], y - point[1]) < 1e-12)


def test_the_rounding_of_the_step_can_change_which_points_a_shell_samples():
    # The default step for 3 mm is 3 * 0.1 = 0.30000000000000004 mm; v0.41.0
    # divided by interp_fraction, 3 / 10 = 0.3 mm. A 2D shell of radius r has
    # ceil(2 pi r / step) + 1 points, so a step that differs only in its last
    # digit can change how many points a shell has and where they lie, and
    # with them gamma and pass or fail.
    #
    # The evaluation dose, 10 + x + y Gy on the square [-a, a] x [-a, a],
    # equals the reference dose, 10 + 2a Gy at the origin, only at the corner
    # (a, a). The last shell has the corners' radius, sqrt(2) a, at which
    # 2 pi r / step is exactly 15 with this step and 15.000000000000004 with
    # v0.41.0's. The 16 points of this step include the corner, at 45 degrees.
    # The 17 points of v0.41.0's miss it, and its search gave gamma 1.55, a
    # fail.
    a = 0.5064279278383723
    corner = (a, a)
    corner_distance = np.hypot(a, a)
    distance_criterion_mm = 3
    step = distance_criterion_mm * shell.DEFAULT_SEARCH_STEP_FRACTION
    divided_step = distance_criterion_mm / 10

    assert step != divided_step
    shell_points = createshells.calculate_coordinates_shell_2d(corner_distance, step)
    assert len(shell_points[0]) == 16
    assert _samples(shell_points, corner)
    divided_points = createshells.calculate_coordinates_shell_2d(
        corner_distance, divided_step
    )
    assert len(divided_points[0]) == 17
    assert not _samples(divided_points, corner)

    axis = np.array([-a, a])
    reference_dose = 10 + 2 * a
    result = pymedphys.gamma(
        (np.array([0.0]), np.array([0.0])),
        np.array([[reference_dose]]),
        (axis, axis),
        10 + axis[:, None] + axis[None, :],
        1,
        distance_criterion_mm,
    )
    gamma = result.gamma.ravel()

    # At the corner the dose difference is zero, so gamma is the corner's
    # distance divided by the distance criterion. The tolerance allows for
    # rounding in the shell point's position and in the interpolated dose,
    # each of order 1e-15 or less here. It is far below the 8e-5 by which this sample
    # exceeds the exact minimum, and the 1.3 by which v0.41.0's exceeded it.
    np.testing.assert_allclose(
        gamma, [corner_distance / distance_criterion_mm], rtol=0, atol=1e-12
    )

    # The search can only overestimate the exact minimum. With a dose gradient
    # of (1, 1) Gy/mm and the dose criterion c, 1% of the reference dose, the
    # minimum is at a point inside the square and is
    # sqrt(2) a / sqrt(3^2 + c^2 / 2).
    dose_criterion = 0.01 * reference_dose
    minimum = (
        np.sqrt(2) * a / np.hypot(distance_criterion_mm, dose_criterion / np.sqrt(2))
    )
    assert gamma[0] >= minimum
    assert (result.analysed, result.passed) == (1, 1)
