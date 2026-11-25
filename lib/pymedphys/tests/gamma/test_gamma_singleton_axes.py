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

"""Gamma against evaluation planes, lines and points (issue #2070).

A singleton evaluation axis makes the evaluation grid a plane, line or point
with no thickness. Gamma must search that support directly, include the
perpendicular distance to it, and not depend on where the origin is.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

INTERPOLATORS = ["pymedphys", "scipy"]
OUTSIDE = "ignore:.*outside the evaluation grid:UserWarning"

A, B, DTA = 0.97, 0.025, 2.0
Y = np.linspace(-3.0, 3.0, 13)
X = np.linspace(-2.0, 2.0, 9)
PLANE_Z = 1.0


def _plane_dose():
    # Linear in y and constant in x, so linear interpolation is exact.
    return (A + B * Y)[:, None] * np.ones_like(X)[None, :]


def _exact_plane_gamma(reference_points, reference_dose, dose_criterion):
    """Minimise gamma over the plane z = PLANE_Z analytically.

    Gamma squared is a convex quadratic in the in-plane position, so its
    minimum is the stationary point clipped to the plane's extent.
    """
    z, y, x = reference_points.T
    h_squared = (z - PLANE_Z) ** 2
    y_star = (y * dose_criterion**2 - B * (A - reference_dose) * DTA**2) / (
        dose_criterion**2 + (B * DTA) ** 2
    )
    y_star = np.clip(y_star, Y[0], Y[-1])
    x_star = np.clip(x, X[0], X[-1])
    return np.sqrt(
        ((A + B * y_star - reference_dose) / dose_criterion) ** 2
        + ((y_star - y) ** 2 + (x_star - x) ** 2 + h_squared) / DTA**2
    )


def _assert_within_search_resolution(result, exact, dose_criterion, step):
    # Sampling can only overestimate gamma. The in-plane search places a
    # candidate within sqrt(2) steps of the optimum, and gamma changes by at
    # most sqrt((B / dose_criterion)^2 + 1 / DTA^2) per millimetre there.
    lipschitz = np.sqrt((B / dose_criterion) ** 2 + 1 / DTA**2)
    assert np.all(result >= exact - 1e-12), (result, exact)
    assert np.all(result - exact <= np.sqrt(2) * step * lipschitz), (result, exact)


@pytest.mark.filterwarnings(OUTSIDE)
@pytest.mark.parametrize("normalisation", ["global", "local"])
@pytest.mark.parametrize("interpolator", INTERPOLATORS)
def test_volume_against_a_plane_matches_the_analytic_minimum(
    interpolator, normalisation
):
    # Reference slices on, beside and well away from the evaluation plane,
    # including points beyond the plane's in-plane extent.
    z = np.array([-0.5, 1.0, 1.4, 4.0])
    y = np.array([-4.0, -1.3, 0.0, 2.2, 3.5])
    x = np.array([-2.5, 0.0, 1.1])
    reference_dose = 1.0 + 0.01 * np.sin(np.add.outer(np.add.outer(z, y), x))

    result = pymedphys.gamma(
        (z, y, x),
        reference_dose,
        (np.array([PLANE_Z]), Y, X),
        _plane_dose()[None],
        3,
        DTA,
        lower_dose_cutoff_percent=0,
        search_step_fraction=0.05,
        normalisation=normalisation,
        interpolator=interpolator,
        memory_budget_bytes=2**14,
    ).gamma

    points = np.stack(np.meshgrid(z, y, x, indexing="ij"), axis=-1).reshape(-1, 3)
    doses = reference_dose.ravel()
    dose_criterion = 0.03 * (
        doses if normalisation == "local" else reference_dose.max()
    )
    exact = _exact_plane_gamma(points, doses, dose_criterion)
    _assert_within_search_resolution(
        result.ravel(), exact, dose_criterion, step=DTA / 20
    )


@pytest.mark.parametrize("interpolator", INTERPOLATORS)
@pytest.mark.parametrize("origin", [0.0, 300.0, -1234.5])
def test_plane_gamma_does_not_depend_on_the_origin(interpolator, origin):
    reference_points = np.array([[PLANE_Z, -1.3, 0.4], [PLANE_Z + 0.5, 0.7, -0.2]])
    reference_dose = np.array([1.0, 1.02])

    results = []
    for shift in (0.0, origin):
        result = pymedphys.gamma(
            tuple(np.array([c]) for c in reference_points[0] + shift),
            reference_dose[:1].reshape(1, 1, 1),
            (np.array([PLANE_Z + shift]), Y + shift, X + shift),
            _plane_dose()[None],
            3,
            DTA,
            interpolator=interpolator,
        ).gamma
        results.append(result.item())

    np.testing.assert_allclose(results[1], results[0], rtol=0, atol=1e-9)


@pytest.mark.filterwarnings(OUTSIDE)
@pytest.mark.parametrize("interpolator", INTERPOLATORS)
@pytest.mark.parametrize("fixed_axis", [0, 1, 2])
def test_the_fixed_axis_can_be_any_axis(interpolator, fixed_axis):
    z = np.array([0.0, 1.0, 2.5])
    y = np.array([-1.3, 0.0, 2.2])
    x = np.array([-0.5, 1.1])
    reference_dose = 1.0 + 0.01 * np.add.outer(np.add.outer(z, y), x)
    evaluation_axes = (np.array([PLANE_Z]), Y, X)
    evaluation_dose = _plane_dose()[None]

    expected = pymedphys.gamma(
        (z, y, x),
        reference_dose,
        evaluation_axes,
        evaluation_dose,
        3,
        DTA,
        interpolator=interpolator,
    ).gamma

    order = [1, 2]
    order.insert(fixed_axis, 0)
    result = pymedphys.gamma(
        tuple((z, y, x)[i] for i in order),
        np.transpose(reference_dose, order),
        tuple(evaluation_axes[i] for i in order),
        np.transpose(evaluation_dose, order),
        3,
        DTA,
        interpolator=interpolator,
    ).gamma

    np.testing.assert_allclose(
        result, np.transpose(expected, order), rtol=0, atol=1e-12
    )


@pytest.mark.parametrize("interpolator", INTERPOLATORS)
def test_coplanar_plane_matches_native_two_dimensional_gamma(interpolator):
    y = np.array([-2.0, -0.7, 0.0, 1.4, 2.6])
    x = np.array([-1.5, 0.3, 1.8])
    reference_dose = 1.0 + 0.02 * np.cos(np.add.outer(y, x))

    native = pymedphys.gamma(
        (y, x), reference_dose, (Y, X), _plane_dose(), 3, DTA, interpolator=interpolator
    ).gamma
    embedded = pymedphys.gamma(
        (np.array([PLANE_Z]), y, x),
        reference_dose[None],
        (np.array([PLANE_Z]), Y, X),
        _plane_dose()[None],
        3,
        DTA,
        interpolator=interpolator,
    ).gamma

    np.testing.assert_allclose(embedded[0], native, rtol=0, atol=1e-12)


@pytest.mark.filterwarnings(OUTSIDE)
@pytest.mark.parametrize("interpolator", INTERPOLATORS)
def test_line_of_evaluation_points(interpolator):
    # An evaluation line along z at (y, x) = (0.5, -1), with uniform dose.
    line_z = np.linspace(-2.0, 2.0, 9)
    reference = (np.array([-3.0, 0.0, 1.0]), np.array([0.5, 2.5]), np.array([-1.0]))
    result = pymedphys.gamma(
        reference,
        np.ones((3, 2, 1)),
        (line_z, np.array([0.5]), np.array([-1.0])),
        np.ones((9, 1, 1)),
        3,
        3,
        interpolator=interpolator,
    ).gamma

    z, y, x = np.meshgrid(*reference, indexing="ij")
    distance = np.sqrt(
        (z - np.clip(z, line_z[0], line_z[-1])) ** 2 + (y - 0.5) ** 2 + (x + 1.0) ** 2
    )
    np.testing.assert_allclose(result, distance / 3, rtol=0, atol=1e-12)


@pytest.mark.filterwarnings(OUTSIDE)
@pytest.mark.parametrize("interpolator", INTERPOLATORS)
@pytest.mark.parametrize("dimensions", [1, 3])
def test_single_evaluation_point(interpolator, dimensions):
    point = np.array([0.5, -1.0, 2.0])[:dimensions]
    reference_axes = tuple(np.array([-1.0, 0.5, 3.0]) for _ in range(dimensions))
    reference_dose = np.full((3,) * dimensions, 1.0)
    reference_dose[(1,) * dimensions] = 1.02

    result = pymedphys.gamma(
        reference_axes,
        reference_dose,
        tuple(np.array([value]) for value in point),
        np.full((1,) * dimensions, 1.01),
        3,
        3,
        interpolator=interpolator,
    ).gamma

    grid = np.stack(np.meshgrid(*reference_axes, indexing="ij"), axis=-1)
    distance = np.linalg.norm(grid - point, axis=-1)
    expected = np.hypot((1.01 - reference_dose) / (0.03 * 1.02), distance / 3)
    np.testing.assert_allclose(result, expected, rtol=0, atol=1e-12)


@pytest.mark.filterwarnings(OUTSIDE)
@pytest.mark.parametrize("interpolator", INTERPOLATORS)
def test_plane_with_gamma_cap_and_several_criteria(interpolator):
    z = np.array([PLANE_Z, PLANE_Z + 3.0, PLANE_Z + 30.0])
    y = np.array([-1.3, 0.0, 2.2])
    x = np.array([0.4])
    reference_dose = np.ones((3, 3, 1))
    common = {
        "lower_dose_cutoff_percent": 0,
        "search_step_fraction": 0.05,
        "interpolator": interpolator,
    }

    uncapped = pymedphys.gamma(
        (z, y, x),
        reference_dose,
        (np.array([PLANE_Z]), Y, X),
        _plane_dose()[None],
        [2, 3],
        [DTA, 3.0],
        **common,
    )
    capped = pymedphys.gamma(
        (z, y, x),
        reference_dose,
        (np.array([PLANE_Z]), Y, X),
        _plane_dose()[None],
        [2, 3],
        [DTA, 3.0],
        gamma_cap=2,
        **common,
    )

    assert len(capped) == len(uncapped) == 4
    for limited, free in zip(capped, uncapped, strict=True):
        distance_criterion = free.settings.distance_criterion_mm
        assert limited.settings.distance_criterion_mm == distance_criterion
        assert (
            limited.settings.dose_criterion_percent
            == free.settings.dose_criterion_percent
        )
        assert np.all(np.isfinite(free.gamma))
        np.testing.assert_array_equal(limited.gamma <= 1, free.gamma <= 1)
        np.testing.assert_allclose(limited.gamma, np.minimum(free.gamma, 2))
        # Beyond the plane by 30 mm, only the perpendicular distance matters.
        assert np.all(free.gamma[2] >= 30 / distance_criterion)
