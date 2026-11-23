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

"""A list of thresholds gives what separate calls give.

Passing several dose or distance thresholds in one call shares work between
them. It must not change any result: the gamma for one pair of thresholds is
the same whether that pair is requested alone or with others.
"""

import itertools

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

OUTSIDE = "outside the evaluation grid"

CONFIGURATIONS = [
    {},
    {"max_gamma": 2},
    {"skip_once_passed": True},
    {"skip_once_passed": True, "max_gamma": 1.5},
    {"local_gamma": True},
    {"local_gamma": True, "skip_once_passed": True},
    {"interp_algo": "scipy"},
    {"random_subset": 200, "random_state": 5, "skip_once_passed": True},
]


def _shifted_noisy_field(shape, shift=2.0, noise=0.04, seed=1):
    """A reference field, and an evaluation shifted along the first axis.

    The noise gives neighbouring evaluation points different doses, so the
    gamma found depends on how finely the search samples between them.
    """
    rng = np.random.default_rng(seed)
    axes = tuple(np.arange(0.0, length) for length in shape)
    grids = np.meshgrid(*axes, indexing="ij")
    centre = [length / 2 for length in shape]
    width = (min(shape) / 5) ** 2

    squared_radius = sum((grid - c) ** 2 for grid, c in zip(grids, centre))
    shifted_squared_radius = (grids[0] - centre[0] - shift) ** 2 + sum(
        (grid - c) ** 2 for grid, c in zip(grids[1:], centre[1:])
    )
    reference = 100 * np.exp(-squared_radius / (2 * width))
    evaluation = 100 * np.exp(-shifted_squared_radius / (2 * width))
    evaluation = evaluation * (1 + noise * rng.standard_normal(shape))

    return axes, reference, evaluation


def _assert_list_equals_separate_calls(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_thresholds,
    distance_thresholds,
    **kwargs,
):
    arguments = (axes_reference, dose_reference, axes_evaluation, dose_evaluation)
    together = pymedphys.gamma(
        *arguments, dose_thresholds, distance_thresholds, **kwargs
    )

    pairs = list(itertools.product(dose_thresholds, distance_thresholds))
    assert list(together) == pairs
    for dose_threshold, distance_threshold in pairs:
        alone = pymedphys.gamma(
            *arguments, dose_threshold, distance_threshold, **kwargs
        )
        np.testing.assert_array_equal(
            together[(dose_threshold, distance_threshold)],
            alone,
            err_msg=f"{dose_threshold}%/{distance_threshold} mm with {kwargs}",
        )


def test_pair_is_unaffected_by_a_smaller_distance_threshold_in_the_same_call():
    # With 1 mm in the same call, 2%/2 mm used to be searched at the 1 mm
    # threshold's step and passed 963 points here, against 941 on its own.
    axes, reference, evaluation = _shifted_noisy_field((60, 50))

    alone = pymedphys.gamma(axes, reference, axes, evaluation, 2, 2)
    together = pymedphys.gamma(axes, reference, axes, evaluation, 2, [2, 1])

    assert np.count_nonzero(~np.isnan(alone)) == 1005
    assert np.count_nonzero(alone <= 1) == 941
    assert np.count_nonzero(together[(2, 2)] <= 1) == 941
    np.testing.assert_array_equal(together[(2, 2)], alone)


@pytest.mark.parametrize("kwargs", CONFIGURATIONS, ids=str)
def test_two_dimensional_list_equals_separate_calls(kwargs):
    axes, reference, evaluation = _shifted_noisy_field((40, 35))

    _assert_list_equals_separate_calls(
        axes, reference, axes, evaluation, [3, 2, 1], [3, 2, 1], **kwargs
    )


@pytest.mark.parametrize(
    "kwargs", [{"max_gamma": 2}, {"skip_once_passed": True}], ids=str
)
def test_three_dimensional_list_equals_separate_calls(kwargs):
    axes, reference, evaluation = _shifted_noisy_field((12, 11, 10), shift=1.0)

    _assert_list_equals_separate_calls(
        axes, reference, axes, evaluation, [3, 2], [3, 1.5], **kwargs
    )


def test_one_dimensional_list_equals_separate_calls():
    (axis,), reference, evaluation = _shifted_noisy_field((80,))

    _assert_list_equals_separate_calls(
        axis, reference, axis, evaluation, [3, 1], [3, 2, 1]
    )


@pytest.mark.parametrize("kwargs", [{}, {"skip_once_passed": True}], ids=str)
def test_list_against_a_single_evaluation_plane_equals_separate_calls(kwargs):
    # The evaluation dose is one plane, so every search adds the reference
    # point's distance from that plane.
    axes, reference, evaluation = _shifted_noisy_field((5, 14, 12), shift=0.0)
    plane_axes = (axes[0][2:3], axes[1], axes[2])
    plane_dose = evaluation[2:3]

    _assert_list_equals_separate_calls(
        axes,
        reference,
        plane_axes,
        plane_dose,
        [3, 2],
        [3, 1.5],
        lower_percent_dose_cutoff=0,
        max_gamma=3,
        **kwargs,
    )


def test_each_listed_pair_matches_the_analytic_minimum_at_its_own_step():
    # Along a linear evaluation dose a + b*x on [0, 3], gamma squared is a
    # convex quadratic in x, so its minimum is the stationary point clipped
    # to the grid. Each pair is searched at its own step, the distance
    # threshold divided by interp_fraction, whatever else is in the list.
    a, b = 0.97, 0.025
    interp_fraction = 20
    dose_thresholds = [3, 2]
    distance_thresholds = [1.0, 2.0, 4.0]
    evaluation_x = np.linspace(0.0, 3.0, 11)
    reference_x = np.array([-1.7, -0.2, 0.3, 1.7, 4.3])
    reference_dose = np.array([0.98, 1.01, 1.02, 0.99, 1.03])

    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            reference_x,
            reference_dose,
            evaluation_x,
            a + b * evaluation_x,
            dose_thresholds,
            distance_thresholds,
            interp_fraction=interp_fraction,
        )

    for dose_threshold, dta in itertools.product(dose_thresholds, distance_thresholds):
        dose_criterion = dose_threshold / 100 * reference_dose.max()
        stationary = (
            reference_x * dose_criterion**2 - b * (a - reference_dose) * dta**2
        ) / (dose_criterion**2 + (b * dta) ** 2)
        nearest = np.clip(stationary, evaluation_x[0], evaluation_x[-1])
        exact = np.hypot(
            (a + b * nearest - reference_dose) / dose_criterion,
            (nearest - reference_x) / dta,
        )
        # The search can only overestimate gamma, by at most one search
        # step times the objective's Lipschitz bound.
        step = dta / interp_fraction
        lipschitz = np.sqrt((b / dose_criterion) ** 2 + 1 / dta**2)
        found = result[(dose_threshold, dta)]
        assert np.all(found >= exact - 1e-12), (dose_threshold, dta, found, exact)
        assert np.all(found - exact <= step * lipschitz), (
            dose_threshold,
            dta,
            found,
            exact,
        )
