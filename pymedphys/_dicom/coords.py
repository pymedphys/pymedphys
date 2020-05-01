# Copyright (C) 2019 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A suite of functions for handling DICOM coordinates"""

from pymedphys._imports import numpy as np


def coords_from_xyz_axes(xyz_axes):
    """Converts a set of x, y and z axes of a regular grid (e.g. a DICOM
    pixel array) into an array of three grids whose voxels correspond to
    and contain the `x`, `y`, and `z` coordinates of the original grid.

    Parameters
    ----------
    xyz_axes : tuple
        A tuple containing three `numpy.ndarray`s corresponding to the `x`,
        `y` and `z` axes of a given 3D grid - usually a DICOM dataset's
        pixel array.

    Returns
    -------
    coords : ndarray
        An array containing three grids consisting of the `x`, 'y` and
        `z` coordinates of the corresponding grid (e.g. DICOM dataset's
        pixel array) from which the original axes were extracted.
    """
    ZZ, YY, XX = np.meshgrid(xyz_axes[2], xyz_axes[1], xyz_axes[0], indexing="ij")

    coords = np.array((XX, YY, ZZ), dtype=np.float64)
    return coords


def _orientation_is_head_first(orientation_vector, is_decubitus):
    if is_decubitus:
        return np.abs(np.sum(orientation_vector)) != 2

    return np.abs(np.sum(orientation_vector)) == 2


def xyz_axes_from_dataset(ds, coord_system="DICOM"):
    r"""Returns the x, y and z axes of a DICOM dataset's
    pixel array in the specified coordinate system.

    For DICOM RT Dose datasets, these are the x, y, z axes of the
    dose grid.

    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        A DICOM dataset that contains pixel data. Supported modalities
        include 'CT' and 'RTDOSE'.

    coord_system : str, optional
        The coordinate system in which to return the `x`, `y` and `z`
        axes of the DICOM dataset. The accepted, case-insensitive
        values of `coord_system` are:

        'DICOM' or 'd':
            Return axes in the DICOM coordinate system.

        'patient', 'IEC patient' or 'p':
            Return axes in the IEC patient coordinate system.

        'fixed', 'IEC fixed' or 'f':
            Return axes in the IEC fixed coordinate system.

    Returns
    -------
    (x, y, z)
        A tuple containing three `numpy.ndarray`s corresponding to the `x`,
        `y` and `z` axes of the DICOM dataset's pixel array in the
        specified coordinate system.

    Notes
    -----
    Supported scan orientations [1]_:

    =========================== ==========================
    Orientation                 ds.ImageOrientationPatient
    =========================== ==========================
    Feet First Decubitus Left   [0, 1, 0, 1, 0, 0]
    Feet First Decubitus Right  [0, -1, 0, -1, 0, 0]
    Feet First Prone            [1, 0, 0, 0, -1, 0]
    Feet First Supine           [-1, 0, 0, 0, 1, 0]
    Head First Decubitus Left   [0, -1, 0, 1, 0, 0]
    Head First Decubitus Right  [0, 1, 0, -1, 0, 0]
    Head First Prone            [-1, 0, 0, 0, -1, 0]
    Head First Supine           [1, 0, 0, 0, 1, 0]
    =========================== ==========================

    References
    ----------
    .. [1] O. McNoleg, "Generalized coordinate transformations for Monte
       Carlo (DOSXYZnrc and VMC++) verifications of DICOM compatible
       radiotherapy treatment plans", arXiv:1406.0014, Table 1,
       https://arxiv.org/ftp/arxiv/papers/1406/1406.0014.pdf
    """

    position = np.array(ds.ImagePositionPatient)
    orientation = np.array(ds.ImageOrientationPatient)

    if not (
        np.array_equal(np.abs(orientation), np.array([1, 0, 0, 0, 1, 0]))
        or np.array_equal(np.abs(orientation), np.array([0, 1, 0, 1, 0, 0]))
    ):
        raise ValueError(
            "Dose grid orientation is not supported. Dose "
            "grid slices must be aligned along the "
            "superoinferior axis of patient."
        )

    is_decubitus = orientation[0] == 0
    is_head_first = _orientation_is_head_first(orientation, is_decubitus)

    di = float(ds.PixelSpacing[0])
    dj = float(ds.PixelSpacing[1])

    col_range = np.arange(0, ds.Columns * di, di)
    row_range = np.arange(0, ds.Rows * dj, dj)

    if is_decubitus:
        x_dicom_fixed = orientation[1] * position[1] + col_range
        y_dicom_fixed = orientation[3] * position[0] + row_range
    else:
        x_dicom_fixed = orientation[0] * position[0] + col_range
        y_dicom_fixed = orientation[4] * position[1] + row_range

    if is_head_first:
        z_dicom_fixed = position[2] + np.array(ds.GridFrameOffsetVector)
    else:
        z_dicom_fixed = -position[2] + np.array(ds.GridFrameOffsetVector)

    if coord_system.upper() in ("FIXED", "IEC FIXED", "F"):
        x = x_dicom_fixed
        y = z_dicom_fixed
        z = -np.flip(y_dicom_fixed)

    elif coord_system.upper() in ("DICOM", "D", "PATIENT", "IEC PATIENT", "P"):

        if orientation[0] == 1:
            x = x_dicom_fixed
        elif orientation[0] == -1:
            x = np.flip(x_dicom_fixed)
        elif orientation[1] == 1:
            y_d = x_dicom_fixed
        elif orientation[1] == -1:
            y_d = np.flip(x_dicom_fixed)

        if orientation[4] == 1:
            y_d = y_dicom_fixed
        elif orientation[4] == -1:
            y_d = np.flip(y_dicom_fixed)
        elif orientation[3] == 1:
            x = y_dicom_fixed
        elif orientation[3] == -1:
            x = np.flip(y_dicom_fixed)

        if not is_head_first:
            z_d = np.flip(z_dicom_fixed)
        else:
            z_d = z_dicom_fixed

        if coord_system.upper() in ("DICOM", "D"):
            y = y_d
            z = z_d
        elif coord_system.upper() in ("PATIENT", "IEC PATIENT", "P"):
            y = z_d
            z = -np.flip(y_d)

    return (x, y, z)
