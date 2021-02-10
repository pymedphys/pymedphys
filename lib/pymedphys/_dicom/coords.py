# Copyright (C) 2019, 2021 Matthew Jennings

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

from collections import namedtuple
from typing import Sequence, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom  # pylint: disable=unused-import

Axes = namedtuple("Axes", "x y z coord_system, orient")
Coords = namedtuple("Coords", "grid coord_system orient")

# fmt: off
ORIENTATIONS_SUPPORTED = {
    "FFDL": [ 0,  1,  0,  1,  0,  0],
    "FFDR": [ 0, -1,  0, -1,  0,  0],
    "FFP":  [ 1,  0,  0,  0, -1,  0],
    "FFS":  [-1,  0,  0,  0,  1,  0],
    "HFDL": [ 0, -1,  0,  1,  0,  0],
    "HFDR": [ 0,  1,  0, -1,  0,  0],
    "HFP":  [-1,  0,  0,  0, -1,  0],
    "HFS":  [ 1,  0,  0,  0,  1,  0],
}
# fmt: on


def coords_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: str = "IEC FIXED"
) -> Coords:
    r"""Returns the x, y and z coordinates of a DICOM dataset's
    pixel array in the specified coordinate system.


    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        A DICOM dataset that contains pixel data. Supported modalities
        include 'CT' and 'RTDOSE'.

    coord_system : str, optional
        The coordinate system in which to return the `x`, `y` and `z`
        coordinates of the DICOM dataset. The accepted, case-insensitive
        values of `coord_system` are:

        'DICOM' or 'd':
            Return axes in the DICOM coordinate system.

        'patient', 'IEC patient' or 'p':
            Return axes in the IEC patient coordinate system.

        'fixed', 'IEC fixed' or 'f':
            Return axes in the IEC fixed coordinate system.


    Returns
    -------
    coords :
        An array containing three grids consisting of the `x`, 'y` and
        `z` coordinates of the corresponding grid (e.g. DICOM dataset's
        pixel array). E.g. coords[0, k, i, j]


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

    axes = xyz_axes_from_dataset(ds=ds, coord_system=coord_system)
    return coords_from_xyz_axes(xyz_axes=axes)


def coords_from_xyz_axes(xyz_axes: Axes) -> Coords:
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

    is_decubitis = "D" in xyz_axes.orient

    if xyz_axes.coord_system == "D":
        if is_decubitis:
            ZZ, XX, YY = np.meshgrid(
                xyz_axes[2], xyz_axes[0], xyz_axes[1], indexing="ij"
            )
        else:
            ZZ, YY, XX = np.meshgrid(
                xyz_axes[2], xyz_axes[1], xyz_axes[0], indexing="ij"
            )

    elif xyz_axes.coord_system in ("F", "P"):
        if xyz_axes.coord_system == "P" and is_decubitis:
            YY, XX, ZZ = np.meshgrid(
                xyz_axes[1], xyz_axes[0], xyz_axes[2], indexing="ij"
            )
        else:
            YY, ZZ, XX = np.meshgrid(
                xyz_axes[1], xyz_axes[2], xyz_axes[0], indexing="ij"
            )
    else:
        raise ValueError("Invalid coordinate system")

    return Coords(
        np.array((XX, YY, ZZ), dtype=np.float64), xyz_axes.coord_system, xyz_axes.orient
    )


def _orientation_is_head_first(orientation_vector, is_decubitus):
    if is_decubitus:
        return np.abs(np.sum(orientation_vector)) != 2

    return np.abs(np.sum(orientation_vector)) == 2


def xyz_axes_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: str = "IEC FIXED"
) -> Axes:
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

    if coord_system.upper() in ("FIXED", "IEC FIXED", "F"):
        coord_system = "F"
    elif coord_system.upper() in ("PATIENT", "IEC PATIENT", "P"):
        coord_system = "P"
    elif coord_system.upper() in ("DICOM", "D"):
        coord_system = "D"

    position = np.array(ds.ImagePositionPatient)
    orientation = np.array(ds.ImageOrientationPatient)
    orient_str = next(
        key
        for key, val in ORIENTATIONS_SUPPORTED.items()
        if np.allclose(np.array(val), orientation)
    )

    if not (
        np.allclose(np.abs(orientation), np.array([1, 0, 0, 0, 1, 0]))
        or np.allclose(np.abs(orientation), np.array([0, 1, 0, 1, 0, 0]))
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

    if coord_system == "F":
        x = x_dicom_fixed
        y = z_dicom_fixed
        z = -y_dicom_fixed

    elif coord_system in ("P", "D"):
        if is_decubitus:
            x = orientation[3] * y_dicom_fixed
            y_dicom = orientation[1] * x_dicom_fixed
        else:
            x = orientation[0] * x_dicom_fixed
            y_dicom = orientation[4] * y_dicom_fixed

        if is_head_first:
            z_dicom = z_dicom_fixed
        else:
            z_dicom = -z_dicom_fixed

        if coord_system == "D":
            y = y_dicom
            z = z_dicom
        elif coord_system == "P":
            y = z_dicom
            z = -y_dicom

    return Axes(x, y, z, coord_system, orient_str)


def coords_in_datasets_are_equal(datasets: Sequence["pydicom.dataset.Dataset"]) -> bool:
    """True if all DICOM datasets have perfectly matching coordinates

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM datasets whose coordinates are to be
        compared.

    Returns
    -------
    bool
        True if coordinates match for all datasets, False otherwise.
    """

    # Quick shape (sanity) check
    if not all(
        ds.pixel_array.shape == datasets[0].pixel_array.shape for ds in datasets
    ):
        return False

    # Full coord check:
    all_concat_axes = [np.concatenate(xyz_axes_from_dataset(ds)) for ds in datasets]

    return all(np.allclose(a, all_concat_axes[0]) for a in all_concat_axes)


def unravelled_argmax(a: "np.ndarray"):
    return np.unravel_index(np.argmax(a), a.shape)
