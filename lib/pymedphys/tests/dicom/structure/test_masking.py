# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from pymedphys._imports import numpy as np
from pymedphys._imports import shapely

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.dose import get_dose_grid_structure_mask


@pytest.mark.pydicom
def test_structure_dose_mask():
    dx = 0.1
    dy = 0.2

    x0 = -3
    y0 = -1

    epsilon = 0.001
    contour_name = "rectangle"

    x_grid = np.arange(x0, 2, dx)
    y_grid = np.arange(y0, 4, dy)

    xx, yy = np.meshgrid(x_grid, y_grid)

    contour_x = [0, 0, 1, 1]
    contour_y = [0, 2, 2, 0]
    contour_z = [0, 1, 2]

    contour = np.vstack([contour_x, contour_y]).T

    eroded_mask = _shapely_based_masking_with_epsilon_buffer(xx, yy, contour, -epsilon)
    buffered_mask = _shapely_based_masking_with_epsilon_buffer(xx, yy, contour, epsilon)

    structure_dataset, dose_dataset = _convert_contours_to_dummy_dicom_files(
        x_grid, y_grid, contour_x, contour_y, contour_z, contour_name
    )

    x_dicom, y_dicom, z_dicom = xyz_axes_from_dataset(dose_dataset)

    assert np.allclose(x_dicom, x_grid)
    assert np.allclose(y_dicom, y_grid)
    assert np.allclose(z_dicom, contour_z)

    dicom_mask = get_dose_grid_structure_mask(
        contour_name, structure_dataset, dose_dataset
    )

    for i, _ in enumerate(contour_z):
        # All points within the eroded mask are also within the dicom_mask
        assert np.all(np.logical_and(eroded_mask, dicom_mask[i, :, :]) == eroded_mask)

        # All points outside the buffered mask are also outside the dicom_mask
        assert np.all(
            np.logical_and(
                np.logical_not(buffered_mask), np.logical_not(dicom_mask[i, :, :])
            )
            == np.logical_not(buffered_mask)
        )


def _get_grid_spacing(array):
    dx = np.unique(np.round(np.diff(array), 4))
    assert len(dx) == 1

    return dx


def _convert_contours_to_dummy_dicom_files(
    x_grid, y_grid, contour_x, contour_y, contour_z, contour_name
):
    x0 = x_grid[0]
    y0 = y_grid[0]

    dx = _get_grid_spacing(x_grid)
    dy = _get_grid_spacing(y_grid)

    contour_data = []

    for z in contour_z:
        concatenated_contours = []
        for x, y in zip(contour_x, contour_y):
            concatenated_contours.append(x)
            concatenated_contours.append(y)
            concatenated_contours.append(z)

        contour_data.append(concatenated_contours)

    structure_dataset = dicom_dataset_from_dict(
        {
            "StructureSetROISequence": [{"ROINumber": 1, "ROIName": contour_name}],
            "ROIContourSequence": [
                {
                    "ReferencedROINumber": 1,
                    "ContourSequence": [
                        {"ContourData": contour_data[0]},
                        {"ContourData": contour_data[1]},
                        {"ContourData": contour_data[2]},
                    ],
                }
            ],
        }
    )

    # Here the dose grid is forced to align to the contour grid. This is
    # a special case, but as of yet this is the only case supported. In
    # the future, should "nearest neighbour" contour interpolation in
    # the z-axis be implemented, this test case will need to be adjusted
    # to have the dose grid not be aligned with the contour sequence.
    dose_dataset = dicom_dataset_from_dict(
        {
            "Columns": len(x_grid),
            "Rows": len(y_grid),
            "PixelSpacing": [dx, dy],
            "ImagePositionPatient": [x0, y0, contour_z[0]],
            "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],  # HFS
            "GridFrameOffsetVector": contour_z,
        }
    )

    return structure_dataset, dose_dataset


def _create_shapely_points(xx, yy):
    xx_flat, yy_flat = xx.ravel(), yy.ravel()
    points = shapely.geometry.MultiPoint(list(zip(xx_flat, yy_flat)))

    return points


def _shapely_based_masking_with_epsilon_buffer(xx, yy, contour, epsilon):
    shapely_points = _create_shapely_points(xx, yy)
    shapely_contour = shapely.geometry.Polygon(contour)
    with_buffer = shapely_contour.buffer(epsilon)

    points_within_contour = shapely_points.intersection(with_buffer)

    assert points_within_contour.within(with_buffer)

    mask = _loop_based_mask_approach(xx, yy, points_within_contour)

    return mask


def _loop_based_mask_approach(xx, yy, points_within_contour):
    mask = np.zeros_like(xx).astype("bool")

    for point in points_within_contour:
        coord = point.coords.xy
        mask[np.logical_and(xx == coord[0], yy == coord[1])] = True

    return mask
