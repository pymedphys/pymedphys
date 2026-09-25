# Copyright (C) 2019, 2021, 2026 Matthew Jennings

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

from typing import Sequence, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom  # pylint: disable=unused-import


def coords_from_xyz_axes(xyz_axes: Sequence["np.ndarray"]) -> "np.ndarray":
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


# Direction cosines are written as decimal strings, so allow for rounding.
_ORIENTATION_TOLERANCE = 1e-4


def _axis_aligned_orientation(ds) -> "np.ndarray":
    orientation = np.array(ds.ImageOrientationPatient, dtype=np.float64)
    rounded = np.round(orientation)
    is_axis_aligned = np.allclose(orientation, rounded, atol=_ORIENTATION_TOLERANCE)
    magnitudes = np.abs(rounded)
    if not (
        is_axis_aligned
        and (
            np.array_equal(magnitudes, [1, 0, 0, 0, 1, 0])
            or np.array_equal(magnitudes, [0, 1, 0, 1, 0, 0])
        )
    ):
        raise ValueError(
            "Dose grid orientation is not supported. Dose "
            "grid slices must be aligned along the "
            "superoinferior axis of patient."
        )

    return rounded


def _frame_offsets(ds, position, orientation) -> "np.ndarray":
    """Offsets of each frame along the slice normal, from the first frame.

    PS3.3 C.8.8.3.2: a Grid Frame Offset Vector whose first element is zero is
    relative to Image Position (Patient). Otherwise it holds absolute z
    coordinates, which the standard only permits for the orientation
    [1, 0, 0, 0, 1, 0], with the first element equal to the IPP z value.
    """
    offsets = np.array(ds.GridFrameOffsetVector, dtype=np.float64)
    if offsets[0] == 0:
        return offsets

    if not np.array_equal(orientation, [1, 0, 0, 0, 1, 0]) or not np.isclose(
        offsets[0], position[2]
    ):
        raise ValueError(
            "GridFrameOffsetVector does not start at zero, so it must hold "
            "absolute z coordinates. That form is only valid when Image "
            "Orientation (Patient) is [1, 0, 0, 0, 1, 0] and its first element "
            "equals the z value of Image Position (Patient). Got orientation "
            f"{orientation.tolist()}, first offset {offsets[0]} and IPP z "
            f"{position[2]}."
        )

    relative_offsets: "np.ndarray" = offsets - position[2]
    return relative_offsets


def xyz_axes_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: str = "DICOM"
) -> Tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
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
            Return axes in the DICOM patient coordinate system.

        'fixed', 'IEC fixed' or 'f':
            Return axes in the IEC fixed coordinate system, assuming the
            patient is treated in the orientation in which they were
            scanned, with the origin at the DICOM origin.

    Returns
    -------
    (x, y, z)
        A tuple of three contiguous float64 `numpy.ndarray`s.

        For 'DICOM', each axis holds the coordinate along the pixel array
        dimension on which it varies, in pixel order: `z` follows the
        frames, and `x` and `y` follow the columns and rows respectively.
        For decubitus orientations the rows run along `x` and the columns
        along `y`. An axis is descending wherever the scanner stored the
        pixels in descending order (for example `x` for head first prone),
        so these axes can be paired directly with ``ds.pixel_array``. Use
        :func:`pymedphys.dicom.zyx_and_dose_from_dataset` for ascending
        axes with the dose reordered to match.

        For 'fixed', `x` follows the columns and `y` the frames, both in
        pixel order, and `z` follows the rows in ascending order.

    Raises
    ------
    ValueError
        If `coord_system` is not recognised, the orientation is not one of
        those below, or the Grid Frame Offset Vector is invalid.
    NotImplementedError
        If the IEC patient coordinate system is requested. Its previous
        output was incorrect and it has not been validated since.

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

    Extra notes
    -----------
    Each voxel's position follows PS3.3 C.7.6.2.1.1: for the voxel in frame
    ``k``, row ``i`` and column ``j``,
    ``IPP + j * PixelSpacing[1] * r + i * PixelSpacing[0] * c + offset[k] * n``,
    where ``r`` and ``c`` are the row and column direction cosines of Image
    Orientation (Patient) and ``n = r x c``. Note that ``PixelSpacing`` lists
    the spacing between rows first. See
    http://dicom.nema.org/medical/dicom/current/output/chtml/part03/
    sect_10.7.html#sect_10.7.1.3
    """
    system = coord_system.upper()
    if system in ("PATIENT", "IEC PATIENT", "P"):
        raise NotImplementedError(
            "The IEC patient coordinate system is not currently supported."
        )
    if system not in ("DICOM", "D", "FIXED", "IEC FIXED", "F"):
        raise ValueError(
            f"Unrecognised coord_system {coord_system!r}. Use 'DICOM' or 'FIXED'."
        )

    position = np.array(ds.ImagePositionPatient, dtype=np.float64)
    orientation = _axis_aligned_orientation(ds)
    row_cosine, column_cosine = orientation[:3], orientation[3:]
    normal = np.cross(row_cosine, column_cosine)

    row_spacing = float(ds.PixelSpacing[0])
    column_spacing = float(ds.PixelSpacing[1])

    # Positions along each pixel array dimension, as (n, 3) arrays.
    along_columns = position + np.outer(
        np.arange(ds.Columns) * column_spacing, row_cosine
    )
    along_rows = position + np.outer(np.arange(ds.Rows) * row_spacing, column_cosine)
    along_frames = position + np.outer(
        _frame_offsets(ds, position, orientation), normal
    )

    if system in ("FIXED", "IEC FIXED", "F"):
        x = along_columns @ row_cosine
        y = along_frames @ normal
        z = -(along_rows @ column_cosine)[::-1]
    else:
        is_decubitus = orientation[0] == 0
        if is_decubitus:
            x, y = along_rows[:, 0], along_columns[:, 1]
        else:
            x, y = along_columns[:, 0], along_rows[:, 1]
        z = along_frames[:, 2]

    return (
        np.ascontiguousarray(x, dtype=np.float64),
        np.ascontiguousarray(y, dtype=np.float64),
        np.ascontiguousarray(z, dtype=np.float64),
    )


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
