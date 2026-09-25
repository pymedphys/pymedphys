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

"""Gamma must register the two grids correctly, whatever their axis order."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._gamma.api import gamma_dicom
from pymedphys.tests.dicom._synthetic_rtdose import DOSE_GRID_SCALING, rtdose

# Voxel spacing and gamma criteria are chosen so that a one-voxel (2 mm)
# misregistration fails on the dose gradients: 1 mm / 1 % is well under it.
PIXEL_SPACING = (2.0, 2.0)
SHAPE = (3, 9, 11)


def _gaussian_pixels(shape, position, orientation_sign_x):
    frames, rows, columns = shape
    x = position[0] + orientation_sign_x * PIXEL_SPACING[1] * np.arange(columns)
    y = position[1] - PIXEL_SPACING[0] * np.arange(rows)  # prone: rows run to -y
    xx, yy = np.meshgrid(x, y)
    peak = np.exp(-((xx - 90.0) ** 2 + (yy + 208.0) ** 2) / (2 * 4.0**2))
    plane = np.round(peak / DOSE_GRID_SCALING * 0.01)
    return np.broadcast_to(plane, (frames, rows, columns))


@pytest.mark.pydicom
@pytest.mark.parametrize("cropped_column", ["first", "last"])
def test_head_first_prone_dose_matches_a_one_column_crop_of_itself(cropped_column):
    position = (100.0, -200.0, 300.0)
    full_pixels = _gaussian_pixels(SHAPE, position, orientation_sign_x=-1)
    reference = rtdose(
        "HFP",
        position=position,
        shape=SHAPE,
        pixel_spacing=PIXEL_SPACING,
        pixel_values=full_pixels,
    )

    if cropped_column == "first":
        # HFP columns run towards -x, so dropping column 0 moves IPP x.
        cropped_position = (position[0] - PIXEL_SPACING[1], *position[1:])
        cropped_pixels = full_pixels[..., 1:]
        cropped_index = 0
    else:
        cropped_position = position
        cropped_pixels = full_pixels[..., :-1]
        cropped_index = SHAPE[2] - 1
    evaluation = rtdose(
        "HFP",
        position=cropped_position,
        shape=(SHAPE[0], SHAPE[1], SHAPE[2] - 1),
        pixel_spacing=PIXEL_SPACING,
        pixel_values=cropped_pixels,
    )

    gamma = gamma_dicom(reference, evaluation, 1, 1, lower_percent_dose_cutoff=10)

    (_, _, x), _ = pymedphys.dicom.zyx_and_dose_from_dataset(reference)
    cropped_x = position[0] - PIXEL_SPACING[1] * cropped_index
    outside_crop = ~np.isclose(x, cropped_x)
    compared = gamma[:, :, outside_crop]
    assert np.any(np.isfinite(compared))
    assert np.all(compared[~np.isnan(compared)] <= 1)


def _grid():
    x = np.linspace(-10.0, 10.0, 21)
    y = np.linspace(-6.0, 6.0, 13)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    dose = 100 * np.exp(-(xx**2 + yy**2) / (2 * 3.0**2))
    return (x, y), dose


def test_descending_evaluation_axes_give_the_same_gamma():
    axes, dose = _grid()
    shifted = np.roll(dose, 1, axis=0)
    expected = pymedphys.gamma(axes, dose, axes, shifted, 2, 2)

    descending_axes = (axes[0][::-1], axes[1][::-1])
    result = pymedphys.gamma(axes, dose, descending_axes, shifted[::-1, ::-1], 2, 2)

    np.testing.assert_allclose(result, expected, equal_nan=True)


def test_uneven_evaluation_axis_falls_back_to_scipy():
    axes, dose = _grid()
    uneven_x = axes[0].copy()
    uneven_x[10:] += 0.5
    evaluation_axes = (uneven_x, axes[1])
    expected = pymedphys.gamma(
        axes, dose, evaluation_axes, dose, 2, 2, interp_algo="scipy"
    )

    with pytest.warns(UserWarning, match="evenly spaced"):
        result = pymedphys.gamma(axes, dose, evaluation_axes, dose, 2, 2)

    np.testing.assert_allclose(result, expected, equal_nan=True)


def test_single_point_evaluation_axis_is_rejected():
    axes, dose = _grid()

    with pytest.raises(ValueError, match="at least two"):
        pymedphys.gamma(axes, dose, (axes[0], np.array([0.0])), dose[:, 6:7], 2, 2)


@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
@pytest.mark.parametrize("max_gamma", [None, 2])
def test_non_overlapping_grids_can_pass_gamma(interp_algo, max_gamma):
    # The nearest equal dose is 1.5 mm or 0.5 mm away, respectively, with a
    # 3 mm distance criterion. Overlapping grid extents are not required.
    result = pymedphys.gamma(
        np.array([0.0, 1.0]),
        np.ones(2),
        np.array([1.5, 2.5]),
        np.ones(2),
        3,
        3,
        interp_fraction=30,
        interp_algo=interp_algo,
        max_gamma=max_gamma,
    )
    np.testing.assert_allclose(result, [0.5, 1 / 6])


def test_scipy_preserves_singleton_spatial_dimensions():
    axes = (np.array([0.0, 1.0]), np.array([2.0]))
    dose = np.ones((2, 1))
    result = pymedphys.gamma(axes, dose, axes, dose, 3, 3, interp_algo="scipy")
    np.testing.assert_array_equal(result, np.zeros_like(dose))


@pytest.mark.timeout(10)
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_search_stops_at_grid_extent_with_large_dose_difference(interp_algo):
    # No need to search thousands of mm beyond a 1 mm evaluation grid just
    # because the dose difference keeps gamma large.
    axes = np.array([0.0, 1.0])
    result = pymedphys.gamma(
        axes, np.ones(2), axes, np.full(2, 100.0), 3, 3, interp_algo=interp_algo
    )
    np.testing.assert_allclose(result, [3300, 3300])


def _exact_1d_gamma(reference_x, evaluation_x, dta):
    """Gamma for equal uniform doses: the distance to the nearest point."""
    evaluation_x = np.asarray(evaluation_x)
    distances = np.abs(np.asarray(reference_x)[:, None] - evaluation_x[None, :])
    return distances.min(axis=1) / dta


def _assert_within_search_resolution(result, expected, interp_fraction=10):
    # Sampling a subset of the candidates can only overestimate gamma, by at
    # most one search step in distance.
    resolution = 1 / interp_fraction
    assert np.all(result >= expected - 1e-12), (result, expected)
    assert np.all(result <= expected + resolution), (result, expected)


def test_search_samples_the_spatial_endpoint():
    # The ordinary 0.3 mm shells miss this narrow grid. The spatial endpoint
    # reaches the last evaluation point from x=-1, despite not being a step
    # multiple. Binary fractions keep the endpoint exactly representable.
    reference_x = np.array([-1.0, 1.0])
    evaluation_x = np.array([0.0625, 0.09375])
    result = pymedphys.gamma(
        reference_x,
        np.ones(2),
        evaluation_x,
        np.ones(2),
        3,
        3,
        interp_algo="scipy",
    )

    expected = _exact_1d_gamma(reference_x, evaluation_x, 3)
    # Only x=-1 is asserted: see the expected failure below for x=1.
    _assert_within_search_resolution(result[:1], expected[:1])


@pytest.mark.timeout(10)
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_search_terminates_on_an_evaluation_grid_narrower_than_a_step(interp_algo):
    # The grids' bounding intervals overlap, but the 0.3 mm shells miss the
    # narrow evaluation interval. This used to search forever.
    reference_x = np.array([-1.0, 0.0, 1.0])
    evaluation_x = np.array([0.04, 0.05])
    result = pymedphys.gamma(
        reference_x,
        np.ones(3),
        evaluation_x,
        np.ones(2),
        3,
        3,
        interp_algo=interp_algo,
    )

    # Points whose search never samples the grid are reported as NaN; any
    # value that is reported must be right.
    finite = np.isfinite(result)
    expected = _exact_1d_gamma(reference_x, evaluation_x, 3)
    _assert_within_search_resolution(result[finite], expected[finite])


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "Search shells step past evaluation grids narrower than one step, so "
        "points they cannot reach are excluded as NaN despite having a gamma."
    ),
)
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_every_point_finds_an_evaluation_grid_narrower_than_a_step(interp_algo):
    reference_x = np.array([-1.0, 0.0, 1.0])
    evaluation_x = np.array([0.04, 0.05])
    result = pymedphys.gamma(
        reference_x,
        np.ones(3),
        evaluation_x,
        np.ones(2),
        3,
        3,
        interp_algo=interp_algo,
    )

    _assert_within_search_resolution(
        result, _exact_1d_gamma(reference_x, evaluation_x, 3)
    )


def test_disjoint_grid_beyond_max_gamma_has_no_candidate():
    result = pymedphys.gamma(
        np.array([0.0, 1.0]),
        np.ones(2),
        np.array([1000.0, 1001.0]),
        np.ones(2),
        3,
        3,
        max_gamma=2,
    )
    assert np.all(np.isnan(result))


@pytest.mark.timeout(10)
def test_far_disjoint_grids_skip_empty_search_shells():
    # A 0.01 mm step from zero would require 100 million empty iterations.
    result = pymedphys.gamma(
        np.array([0.0]),
        np.ones(1),
        np.array([1_000_000.0]),
        np.ones(1),
        3,
        0.1,
        interp_algo="scipy",
    )
    np.testing.assert_allclose(result, [10_000_000])


@pytest.mark.parametrize("axis", [np.array([0, np.nan]), np.array([0, np.inf])])
def test_nonfinite_evaluation_axis_is_rejected(axis):
    with pytest.raises(ValueError, match="finite"):
        pymedphys.gamma(np.array([0.0, 1.0]), np.ones(2), axis, np.ones(2), 3, 3)


def test_nonfinite_reference_axis_is_rejected():
    with pytest.raises(ValueError, match="Reference axis.*finite"):
        pymedphys.gamma(
            np.array([0.0, np.nan]), np.ones(2), np.array([0.0, 1.0]), np.ones(2), 3, 3
        )
