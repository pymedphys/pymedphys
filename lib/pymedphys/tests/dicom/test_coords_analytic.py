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

"""DICOM axes checked against the geometry the standard defines.

Each orientation uses an off-centre grid with non-square pixels, so that a
sign error, a reversed axis, or swapped spacings cannot cancel out.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom import coords, dose

from ._synthetic_rtdose import DOSE_GRID_SCALING, ORIENTATIONS, rtdose, voxel_positions

DECUBITUS = {"FFDL", "FFDR", "HFDL", "HFDR"}


def _expected_pixel_order_axes(ds):
    """DICOM x, y and z along the array axis on which each one varies."""
    positions = voxel_positions(ds)
    slice_axis = positions[:, 0, 0, :]
    row_axis = positions[0, :, 0, :]
    column_axis = positions[0, 0, :, :]

    z = slice_axis[:, 2]
    if ds.ImageOrientationPatient[0] == 0:  # decubitus: rows run along x
        x, y = row_axis[:, 0], column_axis[:, 1]
    else:
        x, y = column_axis[:, 0], row_axis[:, 1]

    return x, y, z


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(ORIENTATIONS))
def test_dicom_axes_match_voxel_positions(orientation):
    ds = rtdose(orientation)

    result = coords.xyz_axes_from_dataset(ds)

    for axis, expected in zip(result, _expected_pixel_order_axes(ds)):
        assert axis.dtype == np.float64
        assert axis.flags.c_contiguous
        np.testing.assert_allclose(axis, expected)


@pytest.mark.pydicom
def test_head_first_prone_x_axis_is_not_mirrored():
    # A worked example: columns run towards -x from IPP x = 100 mm.
    ds = rtdose("HFP", position=(100.0, 0.0, 0.0), pixel_spacing=(1.0, 1.0))

    x, _, _ = coords.xyz_axes_from_dataset(ds)

    np.testing.assert_allclose(x, [100.0, 99.0, 98.0, 97.0, 96.0])


@pytest.mark.pydicom
def test_absolute_slice_offsets_match_relative_offsets():
    relative = rtdose("HFS", slice_offsets=[0.0, 2.5, 5.0])
    absolute = rtdose("HFS", slice_offsets=[300.0, 302.5, 305.0])

    np.testing.assert_allclose(
        coords.xyz_axes_from_dataset(absolute)[2],
        coords.xyz_axes_from_dataset(relative)[2],
    )


@pytest.mark.pydicom
def test_absolute_slice_offsets_require_the_standard_orientation():
    # PS3.3 C.8.8.3.2 only permits absolute offsets for [1, 0, 0, 0, 1, 0].
    ds = rtdose("HFP", slice_offsets=[300.0, 302.5, 305.0])

    with pytest.raises(ValueError, match="GridFrameOffsetVector"):
        coords.xyz_axes_from_dataset(ds)


@pytest.mark.pydicom
def test_unknown_coordinate_system_is_rejected():
    with pytest.raises(ValueError, match="coord_system"):
        coords.xyz_axes_from_dataset(rtdose("HFS"), "nonsense")


@pytest.mark.pydicom
def test_iec_patient_coordinates_are_not_offered():
    with pytest.raises(NotImplementedError):
        coords.xyz_axes_from_dataset(rtdose("HFS"), "PATIENT")


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(ORIENTATIONS))
def test_iec_fixed_axes_project_onto_the_image_axes(orientation):
    # The long-standing IEC fixed convention: x along the row direction r,
    # y along the slice normal r x c, and z = -(position . c) in ascending
    # order, all relative to the DICOM origin.
    ds = rtdose(orientation)
    positions = voxel_positions(ds)
    orientation_cosines = np.array(ds.ImageOrientationPatient, dtype=float)
    r, c = orientation_cosines[:3], orientation_cosines[3:]
    n = np.cross(r, c)

    x, y, z = coords.xyz_axes_from_dataset(ds, "FIXED")

    np.testing.assert_allclose(x, positions[0, 0, :, :] @ r)
    np.testing.assert_allclose(y, positions[:, 0, 0, :] @ n)
    np.testing.assert_allclose(z, -(positions[0, :, 0, :] @ c)[::-1])


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(ORIENTATIONS))
@pytest.mark.parametrize(
    "slice_offsets", [[0.0, 2.5, 5.0], [0.0, -2.5, -5.0], [0.0, 2.5, 7.0]]
)
def test_zyx_and_dose_returns_ascending_axes_aligned_with_the_dose(
    orientation, slice_offsets
):
    ds = rtdose(orientation, slice_offsets=slice_offsets)
    positions = voxel_positions(ds)
    raw = np.asarray(ds.pixel_array, dtype=float) * DOSE_GRID_SCALING

    (z, y, x), dose_grid = dose.zyx_and_dose_from_dataset(ds)

    assert dose_grid.shape == (len(z), len(y), len(x))
    for axis in (z, y, x):
        assert np.all(np.diff(axis) > 0)

    # Every voxel's dose must sit at the coordinates of the voxel it came
    # from, whichever way the scanner ordered the pixel data.
    for k, i, j in np.ndindex(raw.shape):
        px, py, pz = positions[k, i, j]
        index = (
            np.argmin(np.abs(z - pz)),
            np.argmin(np.abs(y - py)),
            np.argmin(np.abs(x - px)),
        )
        assert dose_grid[index] == raw[k, i, j], (orientation, (k, i, j))


@pytest.mark.pydicom
@pytest.mark.parametrize("orientation", sorted(ORIENTATIONS))
@pytest.mark.parametrize("omit_offsets", [False, True])
@pytest.mark.parametrize("omit_slice_count", [False, True])
def test_zyx_and_dose_keeps_a_single_slice_dose_three_dimensional(
    orientation, omit_offsets, omit_slice_count
):
    # pydicom returns a (rows, columns) pixel array when there is one slice,
    # as in planar dose exports.
    ds = rtdose(orientation, shape=(1, 4, 5), slice_offsets=[0.0])
    positions = voxel_positions(ds)[0]
    if omit_offsets:
        del ds.GridFrameOffsetVector
    if omit_slice_count:
        del ds.NumberOfFrames
    raw = np.asarray(ds.pixel_array, dtype=float) * DOSE_GRID_SCALING
    assert raw.ndim == 2

    (z, y, x), dose_grid = dose.zyx_and_dose_from_dataset(ds)

    assert dose_grid.shape == (len(z), len(y), len(x))
    assert sorted(dose_grid.shape) == [1, 4, 5]
    for i, j in np.ndindex(raw.shape):
        px, py, pz = positions[i, j]
        index = (
            np.argmin(np.abs(z - pz)),
            np.argmin(np.abs(y - py)),
            np.argmin(np.abs(x - px)),
        )
        assert dose_grid[index] == raw[i, j], (orientation, (i, j))


@pytest.mark.pydicom
def test_multi_slice_dose_requires_slice_offsets():
    ds = rtdose("HFS")
    del ds.GridFrameOffsetVector
    with pytest.raises(ValueError, match="GridFrameOffsetVector.*multi-slice"):
        dose.zyx_and_dose_from_dataset(ds)


@pytest.mark.pydicom
def test_zyx_and_dose_leaves_head_first_supine_unchanged():
    ds = rtdose("HFS")

    (z, y, x), dose_grid = dose.zyx_and_dose_from_dataset(ds)

    np.testing.assert_array_equal(
        dose_grid, np.asarray(ds.pixel_array) * DOSE_GRID_SCALING
    )
    expected_x, expected_y, expected_z = _expected_pixel_order_axes(ds)
    np.testing.assert_allclose(x, expected_x)
    np.testing.assert_allclose(y, expected_y)
    np.testing.assert_allclose(z, expected_z)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "orientation, expected",
    [("HFP", [94.0, -202.0, 302.5]), ("FFDL", [102.0, -194.0, 297.5])],
)
def test_matrix_oracle_matches_worked_voxel_positions(orientation, expected):
    # Slice 1, row 1, column 2 with IPP (100, -200, 300) and spacing (2, 3).
    np.testing.assert_array_equal(
        voxel_positions(rtdose(orientation))[1, 1, 2], expected
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "offsets, message",
    [
        ([], "non-empty"),
        ([0, 2.5], "NumberOfFrames"),
        ([0, 5, 2.5], "monotonic"),
        ([0, 2.5, 2.5], "monotonic"),
        ([0, np.nan, 5], "finite"),
        ([0, 2.5, np.inf], "finite"),
        ([301, 303.5, 306], "Image Position"),
    ],
)
def test_invalid_slice_offsets_are_rejected(offsets, message):
    ds = rtdose("HFS", slice_offsets=offsets)
    with pytest.raises(ValueError, match=message):
        dose.zyx_and_dose_from_dataset(ds)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "attribute, value",
    [
        ("ImagePositionPatient", [np.nan, 0, 0]),
        ("PixelSpacing", [0, 3]),
        ("PixelSpacing", [-2, 3]),
        ("PixelSpacing", [np.inf, 3]),
    ],
)
def test_invalid_image_geometry_is_rejected(attribute, value):
    ds = rtdose("HFS")
    setattr(ds, attribute, value)
    with pytest.raises(ValueError, match=attribute):
        dose.zyx_and_dose_from_dataset(ds)


@pytest.mark.pydicom
def test_geometry_equality_accounts_for_pixel_dimension_mapping():
    # Both datasets describe the same physical dose field. The FFDL dataset
    # stores x along rows and y along columns, and reverses its slice offsets
    # to retain the same patient z positions as HFS.
    pixels = np.arange(3 * 4 * 4).reshape(3, 4, 4)
    reference = rtdose(
        "HFS", shape=pixels.shape, pixel_spacing=(2, 2), pixel_values=pixels
    )
    transposed = rtdose(
        "FFDL",
        shape=pixels.shape,
        pixel_spacing=(2, 2),
        slice_offsets=[0, -2.5, -5],
        pixel_values=pixels.swapaxes(1, 2),
    )
    for ds in (reference, transposed):
        ds.PatientID = "SYNTHETIC"

    np.testing.assert_array_equal(
        voxel_positions(reference), voxel_positions(transposed).swapaxes(1, 2)
    )
    np.testing.assert_array_equal(
        dose.zyx_and_dose_from_dataset(reference)[1],
        dose.zyx_and_dose_from_dataset(transposed)[1],
    )
    assert not coords.coords_in_datasets_are_equal([reference, transposed])
    with pytest.raises(ValueError, match="coincident coordinates"):
        dose.sum_doses_in_datasets([reference, transposed])


@pytest.mark.pydicom
def test_absolute_and_relative_offsets_have_the_same_pixel_mapping():
    relative = rtdose("HFS", slice_offsets=[0, 2.5, 5])
    absolute = rtdose("HFS", slice_offsets=[300, 302.5, 305])
    assert coords.coords_in_datasets_are_equal([relative, absolute])


@pytest.mark.pydicom
def test_rounded_orientation_preserves_geometry():
    expected = rtdose("HFDL")
    rounded = rtdose("HFDL")
    rounded.ImageOrientationPatient = [0.00001, -0.99999, 0, 0.99999, 0.00001, 0]
    for actual, axis in zip(
        coords.xyz_axes_from_dataset(rounded), coords.xyz_axes_from_dataset(expected)
    ):
        np.testing.assert_array_equal(actual, axis)


@pytest.mark.pydicom
def test_oblique_grid_cannot_be_represented_by_patient_axes():
    ds = rtdose("HFS")
    ds.ImageOrientationPatient = [0.8, 0.6, 0, -0.6, 0.8, 0]
    with pytest.raises(ValueError, match="orientation is not supported"):
        coords.xyz_axes_from_dataset(ds)
