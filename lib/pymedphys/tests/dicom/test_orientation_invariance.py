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

"""Physical results must not depend on how an RT Dose grid is stored.

The fixture starts with known patient coordinates and dose values. A manually
worked table encodes that same grid in each orientation, independently of both
the production geometry helper and the matrix oracle in _synthetic_rtdose.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._dicom import collection, create, dose
from pymedphys._gamma.api import gamma_dicom

from ._synthetic_rtdose import DOSE_GRID_SCALING, rtdose, voxel_positions

# Raw (slice, row, column) dimensions expressed as patient (z, y, x)
# dimensions, followed by the direction of travel along each raw dimension.
# For example HFDL stores +z slices, +x rows and -y columns.
STORAGE_ORDER = {
    "HFS": ((0, 1, 2), (1, 1, 1)),
    "HFP": ((0, 1, 2), (1, -1, -1)),
    "FFS": ((0, 1, 2), (-1, 1, -1)),
    "FFP": ((0, 1, 2), (-1, -1, 1)),
    "HFDL": ((0, 2, 1), (1, 1, -1)),
    "HFDR": ((0, 2, 1), (1, -1, 1)),
    "FFDL": ((0, 2, 1), (-1, 1, 1)),
    "FFDR": ((0, 2, 1), (-1, -1, -1)),
}


def _physical_grid():
    axes = (
        311.0 + 2.5 * np.arange(3),
        -213.0 + 2.0 * np.arange(4),
        97.0 + 3.0 * np.arange(5),
    )
    k, i, j = np.indices((3, 4, 5))
    # Unequal dimensions, unequal spacing, an off-centre origin, and an
    # asymmetric dose field expose sign, permutation and registration errors.
    pixels = 20000 + 1301 * k + 311 * i + 71 * j + 31 * i * j + 67 * i * k
    return axes, pixels


def _encode_grid(orientation, axes, pixels, reverse_slices=False):
    dimensions, signs = STORAGE_ORDER[orientation]
    raw = pixels.transpose(dimensions)
    raw_axes = []
    for dimension, (patient_dimension, sign) in enumerate(zip(dimensions, signs)):
        axis = axes[patient_dimension]
        if sign < 0:
            raw = np.flip(raw, axis=dimension)
            axis = axis[::-1]
        raw_axes.append(axis)
    if reverse_slices:
        raw = raw[::-1]
        raw_axes[0] = raw_axes[0][::-1]

    position = np.empty(3)
    for dimension, axis in zip(dimensions, raw_axes):
        position[2 - dimension] = axis[0]
    return rtdose(
        orientation,
        position=position,
        shape=raw.shape,
        pixel_spacing=(
            abs(raw_axes[1][1] - raw_axes[1][0]),
            abs(raw_axes[2][1] - raw_axes[2][0]),
        ),
        slice_offsets=(raw_axes[0] - raw_axes[0][0]) * signs[0],
        pixel_values=raw,
    )


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(STORAGE_ORDER))
@pytest.mark.parametrize("reverse_slices", [False, True])
def test_all_encodings_recover_the_same_physical_grid(orientation, reverse_slices):
    axes, pixels = _physical_grid()
    dataset = _encode_grid(orientation, axes, pixels, reverse_slices)

    actual_axes, actual_dose = dose.zyx_and_dose_from_dataset(dataset)

    for actual, expected in zip(actual_axes, axes):
        np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual_dose, pixels * DOSE_GRID_SCALING)


@pytest.mark.pydicom
@pytest.mark.parametrize("reference_orientation", sorted(STORAGE_ORDER))
@pytest.mark.parametrize("evaluation_orientation", sorted(STORAGE_ORDER))
@pytest.mark.parametrize("interp_algo", ["pymedphys", "scipy"])
def test_gamma_is_invariant_for_every_orientation_pair(
    reference_orientation, evaluation_orientation, interp_algo
):
    axes, pixels = _physical_grid()
    reference = _encode_grid(reference_orientation, axes, pixels)
    options = {
        "dose_percent_threshold": 3,
        "distance_mm_threshold": 3,
        "lower_percent_dose_cutoff": 0,
        "max_gamma": 2,
        "interp_algo": interp_algo,
    }
    # Check equality AND a dose discrepancy. Self-comparisons alone can pass
    # even when both grids have the same incorrect coordinate mapping.
    for difference in (0, 1400):
        evaluation = _encode_grid(
            evaluation_orientation, axes, pixels + difference, reverse_slices=True
        )
        expected = pymedphys.gamma(
            axes,
            pixels * DOSE_GRID_SCALING,
            axes,
            (pixels + difference) * DOSE_GRID_SCALING,
            **options,
        )
        actual = gamma_dicom(reference, evaluation, **options)
        assert np.all(np.isfinite(actual))
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)
        if difference == 0:
            np.testing.assert_allclose(actual, 0, rtol=0, atol=1e-12)
        else:
            assert np.any(expected > 1)


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(STORAGE_ORDER))
@pytest.mark.parametrize("dimension", range(3))
@pytest.mark.parametrize("end", ["first", "last"])
def test_same_orientation_crop_retains_physical_registration(
    orientation, dimension, end
):
    axes, pixels = _physical_grid()
    selection = [slice(None)] * 3
    selection[dimension] = slice(1, None) if end == "first" else slice(None, -1)
    cropped_axes = tuple(axis[item] for axis, item in zip(axes, selection))
    cropped = _encode_grid(
        orientation, cropped_axes, pixels[tuple(selection)], reverse_slices=True
    )
    full = _encode_grid(orientation, axes, pixels)

    # Every reference voxel is also in the full evaluation grid. No search
    # outside the crop is needed, so the exact gamma is zero everywhere.
    result = gamma_dicom(cropped, full, 1, 1, lower_percent_dose_cutoff=0, max_gamma=2)
    assert result.shape == pixels[tuple(selection)].shape
    assert np.all(np.isfinite(result))
    np.testing.assert_allclose(result, 0, rtol=0, atol=1e-12)


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(STORAGE_ORDER))
def test_dicom_interpolation_uses_physical_coordinates(orientation):
    axes, pixels = _physical_grid()
    dataset = _encode_grid(orientation, axes, pixels, reverse_slices=True)
    # The field is multilinear in the voxel indices, so its value halfway
    # between all adjacent voxels is exactly the mean of the eight corners.
    query_axes = tuple((axis[:-1] + axis[1:]) / 2 for axis in axes)
    expected = (
        sum(pixels[k : k + 2, i : i + 3, j : j + 4] for k, i, j in np.ndindex(2, 2, 2))
        / 8
        * DOSE_GRID_SCALING
    )

    actual = dose.dicom_dose_interpolate(query_axes, dataset)

    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", ["FFDL", "FFDR", "HFDL", "HFDR"])
@pytest.mark.parametrize("square", [False, True])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Pre-existing decubitus structure masks do not follow raw pixel dimensions",
)
def test_decubitus_structure_mask_matches_raw_dose(orientation, square):
    axes, pixels = _physical_grid()
    if square:
        axes = (*axes[:2], axes[2][:-1])
        pixels = pixels[..., :-1]
    dataset = _encode_grid(orientation, axes, pixels)
    contours = [
        {"ContourData": [99, -212, z, 105, -212, z, 105, -210, z, 99, -210, z]}
        for z in axes[0]
    ]
    structure = create.dicom_dataset_from_dict(
        {
            "StructureSetROISequence": [{"ROINumber": 1, "ROIName": "box"}],
            "ROIContourSequence": [
                {"ReferencedROINumber": 1, "ContourSequence": contours}
            ],
        }
    )
    # A rectangle containing two columns and one row in patient space. Its
    # transpose differs even when rows and columns have the same length.
    selected = np.zeros_like(pixels)
    selected[:, 1, 1:3] = 1
    expected = _encode_grid(orientation, axes, selected).pixel_array.astype(bool)

    actual = dose.get_dose_grid_structure_mask("box", structure, dataset)

    np.testing.assert_array_equal(actual, expected)


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", ["FFDL", "FFDR", "HFDL", "HFDR"])
@pytest.mark.parametrize("square", [False, True])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Pre-existing DicomDose.coords does not follow decubitus pixel dimensions",
)
def test_decubitus_collection_coordinates_match_raw_dose(orientation, square):
    axes, pixels = _physical_grid()
    if square:
        axes = (*axes[:2], axes[2][:-1])
        pixels = pixels[..., :-1]
    dataset = _encode_grid(orientation, axes, pixels)
    # Use the independent matrix oracle to verify each raw voxel's position.
    expected = voxel_positions(dataset).transpose(3, 0, 1, 2)

    actual = collection.DicomDose(dataset).coords

    np.testing.assert_array_equal(actual, expected)
