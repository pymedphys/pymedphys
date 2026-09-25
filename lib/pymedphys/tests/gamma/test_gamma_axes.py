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


def test_non_overlapping_grids_are_rejected():
    axes, dose = _grid()
    far_away = (axes[0] + 1000.0, axes[1])

    with pytest.raises(ValueError, match="overlap"):
        pymedphys.gamma(axes, dose, far_away, dose, 2, 2)
