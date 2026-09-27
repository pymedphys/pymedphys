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

"""What gamma reports, which points it excludes, and which inputs it rejects.

NaN in the output means only that a point was not analysed: it is below the
lower dose cutoff, or was not selected by ``random_subset``. Every analysed
point has a gamma value, including points outside the evaluation grid.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

OUTSIDE = "outside the evaluation grid"


def _box_2d(dose=1.0):
    axes = (np.linspace(0.0, 4.0, 9), np.linspace(0.0, 4.0, 9))
    return axes, np.full((9, 9), dose)


@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_point_outside_the_grid_gets_gamma_to_the_nearest_edge_point(interp_algo):
    # A uniform evaluation dose: every evaluation point has the same dose
    # difference, so gamma is minimised at the nearest point of the grid's
    # bounding box. For (-2, 7) against [0, 4] x [0, 4] that is (0, 4).
    evaluation_axes, evaluation_dose = _box_2d(dose=1.02)
    reference_axes = (np.array([-2.0, 1.0]), np.array([2.0, 7.0]))

    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            reference_axes,
            np.ones((2, 2)),
            evaluation_axes,
            evaluation_dose,
            3,
            3,
            lower_percent_dose_cutoff=0,
            interp_algo=interp_algo,
        )

    dose_term = 0.02 / 0.03
    nearest = np.array([[(0.0, 2.0), (0.0, 4.0)], [(1.0, 2.0), (1.0, 4.0)]])
    points = np.stack(np.meshgrid(*reference_axes, indexing="ij"), axis=-1)
    distances = np.linalg.norm(points - nearest, axis=-1)
    expected = np.hypot(dose_term, distances / 3)
    np.testing.assert_allclose(result, expected, rtol=0, atol=1e-12)


@pytest.mark.parametrize("local_gamma", [False, True])
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_linear_dose_gradient_matches_the_analytic_minimum(interp_algo, local_gamma):
    # Along a linear evaluation dose a + b*x on [0, 3], gamma squared is a
    # convex quadratic in x, so its minimum is the stationary point clipped
    # to the grid. Reference points lie inside, just outside and well
    # outside the grid on both sides.
    a, b, dta = 0.97, 0.025, 2.0
    evaluation_x = np.linspace(0.0, 3.0, 11)
    reference_x = np.array([-1.7, -0.2, 0.3, 1.7, 4.3])
    reference_dose = np.array([0.98, 1.01, 1.02, 0.99, 1.03])

    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            reference_x,
            reference_dose,
            evaluation_x,
            a + b * evaluation_x,
            3,
            dta,
            interp_fraction=100,
            local_gamma=local_gamma,
            interp_algo=interp_algo,
        )

    dose_criterion = 0.03 * (reference_dose if local_gamma else reference_dose.max())
    stationary = (
        reference_x * dose_criterion**2 - b * (a - reference_dose) * dta**2
    ) / (dose_criterion**2 + (b * dta) ** 2)
    nearest = np.clip(stationary, evaluation_x[0], evaluation_x[-1])
    exact = np.hypot(
        (a + b * nearest - reference_dose) / dose_criterion,
        (nearest - reference_x) / dta,
    )
    # The search can only overestimate gamma, by at most one search step
    # (dta / interp_fraction) times the objective's Lipschitz bound.
    step = dta / 100
    lipschitz = np.sqrt((b / dose_criterion) ** 2 + 1 / dta**2)
    assert np.all(result >= exact - 1e-12), (result, exact)
    assert np.all(result - exact <= step * lipschitz), (result, exact)


@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_three_dimensional_point_outside_the_grid(interp_algo):
    axis = np.linspace(0.0, 2.0, 5)
    reference_axes = (np.array([3.0]), np.array([-1.0]), np.array([1.0]))

    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            reference_axes,
            np.ones((1, 1, 1)),
            (axis, axis, axis),
            np.ones((5, 5, 5)),
            3,
            3,
            interp_algo=interp_algo,
        )

    # The nearest evaluation point is (2, 0, 1).
    np.testing.assert_allclose(result.ravel(), [np.sqrt(2) / 3], rtol=0, atol=1e-12)


@pytest.mark.parametrize("max_gamma", [1.5, 2, 10])
def test_max_gamma_never_changes_pass_or_fail(max_gamma):
    # Reference points span from well inside to far outside the evaluation
    # grid, so some would pass and some fail without a cap.
    reference_x = np.linspace(-40.0, 10.0, 101)
    evaluation_x = np.linspace(0.0, 10.0, 21)
    reference_dose = 1 + 0.001 * reference_x
    evaluation_dose = 1 + 0.001 * evaluation_x + 0.01

    def gamma(**kwargs):
        with pytest.warns(UserWarning, match=OUTSIDE):
            return pymedphys.gamma(
                reference_x,
                reference_dose,
                evaluation_x,
                evaluation_dose,
                3,
                3,
                lower_percent_dose_cutoff=0,
                **kwargs,
            )

    uncapped = gamma()
    capped = gamma(max_gamma=max_gamma)

    assert np.all(np.isfinite(uncapped))
    assert np.any(uncapped <= 1) and np.any(uncapped > max_gamma)
    np.testing.assert_array_equal(capped <= 1, uncapped <= 1)
    np.testing.assert_allclose(capped, np.minimum(uncapped, max_gamma))


def test_points_beyond_max_gamma_fail_at_max_gamma():
    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            np.array([0.0, 1.0]),
            np.ones(2),
            np.array([1000.0, 1001.0]),
            np.ones(2),
            3,
            3,
            max_gamma=2,
        )
    np.testing.assert_array_equal(result, [2, 2])


def test_only_points_not_analysed_are_nan():
    # Points at |x| = 5 and 6 are beyond max_gamma * DTA = 4.5 mm from the
    # grid, but are still analysed and so must still get a value.
    reference_x = np.arange(-8.0, 9.0)
    reference_dose = np.where(np.abs(reference_x) > 6, 0.1, 1.0)

    with pytest.warns(UserWarning, match=OUTSIDE):
        result = pymedphys.gamma(
            reference_x,
            reference_dose,
            np.array([-1.0, 0.0, 1.0]),
            np.ones(3),
            3,
            3,
            max_gamma=1.5,
        )

    np.testing.assert_array_equal(np.isnan(result), reference_dose < 0.2)


def test_outside_warning_reports_the_count_and_fraction():
    # Two of the five analysed points are more than one search step
    # (0.3 mm) outside the grid; the point below the cutoff is not counted.
    with pytest.warns(UserWarning, match=r"2 of 5 analysed reference points \(40"):
        pymedphys.gamma(
            np.array([-2.0, -0.2, 0.0, 1.0, 3.0, 9.0]),
            np.array([1.0, 1.0, 1.0, 1.0, 1.0, 0.0]),
            np.array([0.0, 1.0]),
            np.ones(2),
            3,
            3,
        )


@pytest.mark.filterwarnings("error::UserWarning")
def test_no_warning_within_one_search_step_of_the_grid():
    # 0.2 mm outside is within the method's 0.3 mm resolution for 3 mm.
    result = pymedphys.gamma(
        np.array([-0.2, 0.5, 1.2]),
        np.ones(3),
        np.array([0.0, 1.0]),
        np.ones(2),
        3,
        3,
    )
    np.testing.assert_allclose(result, [0.2 / 3, 0, 0.2 / 3], atol=1e-12)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("which", ["reference", "evaluation"])
def test_non_finite_dose_is_rejected(value, which):
    axis = np.array([0.0, 1.0, 2.0])
    reference = np.ones(3)
    evaluation = np.ones(3)
    (reference if which == "reference" else evaluation)[1] = value

    with pytest.raises(ValueError, match=f"dose_{which}.*finite"):
        pymedphys.gamma(axis, reference, axis, evaluation, 3, 3)


def test_nan_reference_error_names_the_opt_in():
    axis = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="exclude_nan_reference=True"):
        pymedphys.gamma(axis, np.array([1.0, np.nan, 1.0]), axis, np.ones(3), 3, 3)


def test_nan_evaluation_error_recommends_cropping_or_swapping_roles():
    axis = np.array([0.0, 1.0, 2.0])
    with pytest.raises(
        ValueError, match="(?s)Crop the evaluation grid.*as the reference"
    ):
        pymedphys.gamma(axis, np.ones(3), axis, np.array([1.0, np.nan, 1.0]), 3, 3)


@pytest.mark.parametrize(
    ("reference", "evaluation"),
    [
        ([1.0, np.nan, 1.0], [1.0, np.nan, 1.0]),
        ([1.0, np.inf, 1.0], [1.0, 1.0, 1.0]),
        ([1.0, -np.inf, 1.0], [1.0, 1.0, 1.0]),
        ([1.0, 1.0, 1.0], [1.0, np.inf, 1.0]),
    ],
)
def test_opt_in_excludes_only_nan_reference_points(reference, evaluation):
    axis = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="finite"):
        pymedphys.gamma(
            axis,
            np.array(reference),
            axis,
            np.array(evaluation),
            3,
            3,
            exclude_nan_reference=True,
        )


@pytest.mark.parametrize("local_gamma", [False, True])
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_nan_reference_points_are_not_analysed(interp_algo, local_gamma):
    axis = np.arange(6.0)
    reference = np.array([0.9, np.nan, 1.0, 0.95, np.nan, 1.02])
    evaluation = np.array([0.92, 1.0, 1.01, 0.97, 0.99, 1.0])
    options = {"local_gamma": local_gamma, "interp_algo": interp_algo}

    result = pymedphys.gamma(
        axis, reference, axis, evaluation, 3, 1, exclude_nan_reference=True, **options
    )

    # The same points, excluded instead by the lower dose cutoff.
    below_cutoff = np.where(np.isnan(reference), 0.01, reference)
    expected = pymedphys.gamma(axis, below_cutoff, axis, evaluation, 3, 1, **options)

    np.testing.assert_array_equal(np.isnan(result), np.isnan(reference))
    np.testing.assert_array_equal(result, expected)


def test_default_normalisation_ignores_nan_reference_points():
    axis = np.arange(4.0)
    reference = np.array([np.nan, 1.0, 0.8, 0.9])
    evaluation = np.array([1.0, 1.02, 0.83, 0.9])

    def gamma(**kwargs):
        return pymedphys.gamma(
            axis,
            reference,
            axis,
            evaluation,
            3,
            1,
            exclude_nan_reference=True,
            **kwargs,
        )

    np.testing.assert_array_equal(gamma(), gamma(global_normalisation=1.0))


def test_random_subset_selects_only_non_nan_reference_points():
    axis = np.arange(20.0)
    reference = np.where(np.arange(20) % 2 == 0, 1.0, np.nan)
    result = pymedphys.gamma(
        axis,
        reference,
        axis,
        np.ones(20),
        3,
        3,
        random_subset=100,
        random_state=0,
        exclude_nan_reference=True,
    )
    np.testing.assert_array_equal(np.isnan(result), np.isnan(reference))


def test_all_nan_reference_is_rejected():
    axis = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="no finite"):
        pymedphys.gamma(
            axis, np.full(2, np.nan), axis, np.ones(2), 3, 3, exclude_nan_reference=True
        )


@pytest.mark.parametrize("max_gamma", [1, 0.5, 0, np.nan])
def test_max_gamma_that_could_hide_a_fail_is_rejected(max_gamma):
    axis = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="max_gamma"):
        pymedphys.gamma(axis, np.ones(2), axis, np.ones(2), 3, 3, max_gamma=max_gamma)


@pytest.mark.parametrize("global_normalisation", [0, -1, np.nan, np.inf])
def test_unusable_global_normalisation_is_rejected(global_normalisation):
    axis = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="global_normalisation"):
        pymedphys.gamma(
            axis,
            np.ones(2),
            axis,
            np.ones(2),
            3,
            3,
            global_normalisation=global_normalisation,
        )


def test_all_zero_reference_is_rejected():
    axis = np.array([0.0, 1.0])
    with pytest.raises(ValueError, match="global_normalisation"):
        pymedphys.gamma(axis, np.zeros(2), axis, np.ones(2), 3, 3)


def test_local_gamma_at_zero_reference_dose_is_rejected():
    axis = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="lower_percent_dose_cutoff"):
        pymedphys.gamma(
            axis,
            np.array([0.0, 1.0, 1.0]),
            axis,
            np.ones(3),
            3,
            3,
            lower_percent_dose_cutoff=0,
            local_gamma=True,
        )


def test_local_gamma_ignores_zero_dose_below_the_cutoff():
    axis = np.array([0.0, 1.0, 2.0])
    result = pymedphys.gamma(
        axis,
        np.array([0.0, 1.0, 1.0]),
        axis,
        np.ones(3),
        3,
        3,
        local_gamma=True,
    )
    np.testing.assert_array_equal(np.isnan(result), [True, False, False])
