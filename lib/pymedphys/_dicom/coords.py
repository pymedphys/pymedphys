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

import warnings
from dataclasses import dataclass
from itertools import combinations
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

# Keep arithmetic round-off separate from the two physical acceptance limits.
# None of these limits is a threshold for clinical significance.
_NUMERICAL_TOLERANCE_MM = 1e-9
_COORDINATE_QUIET_TOLERANCE_MM = 0.01
_COORDINATE_ACCEPTANCE_TOLERANCE_MM = 0.1
_ABSOLUTE_OFFSET_TOLERANCE_MM = 0.01


def _axis_aligned_orientation(ds) -> "np.ndarray":
    orientation = np.array(ds.ImageOrientationPatient, dtype=np.float64)
    rounded = np.round(orientation)
    is_axis_aligned = np.allclose(
        orientation, rounded, rtol=0, atol=_ORIENTATION_TOLERANCE
    )
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


def _slice_offsets(ds, position, orientation) -> "np.ndarray":
    """Offsets of each slice along the slice normal, from the first slice.

    PS3.3 C.8.8.3.2: a Grid Frame Offset Vector whose first element is zero is
    relative to Image Position (Patient). Otherwise it holds absolute z
    coordinates, which the standard only permits for the orientation
    [1, 0, 0, 0, 1, 0], with the first element equal to the IPP z value.
    A single-slice image may omit the vector or leave it empty; its plane is
    defined by IPP.
    """
    value = getattr(ds, "GridFrameOffsetVector", None)
    # pydicom reads an empty numeric element as None, and an empty multi-valued
    # one as a zero-length MultiValue.
    if value is None or (isinstance(value, Sequence) and len(value) == 0):
        if int(getattr(ds, "NumberOfFrames", 1)) != 1:
            raise ValueError("GridFrameOffsetVector is required for a multi-slice dose")
        return np.zeros(1, dtype=np.float64)

    offsets = np.atleast_1d(np.array(value, dtype=np.float64))
    if offsets.ndim != 1 or offsets.size == 0 or not np.all(np.isfinite(offsets)):
        raise ValueError("GridFrameOffsetVector must be a non-empty finite 1D array")
    if offsets.size != int(getattr(ds, "NumberOfFrames", offsets.size)):
        raise ValueError("GridFrameOffsetVector length must match NumberOfFrames")
    differences = np.diff(offsets)
    if not (np.all(differences > 0) or np.all(differences < 0)):
        raise ValueError("GridFrameOffsetVector must be strictly monotonic")

    if offsets[0] == 0:
        return offsets

    if not np.array_equal(orientation, [1, 0, 0, 0, 1, 0]) or not np.isclose(
        offsets[0], position[2], rtol=0, atol=_ABSOLUTE_OFFSET_TOLERANCE_MM
    ):
        raise ValueError(
            "GridFrameOffsetVector does not start at zero, so it must hold "
            "absolute z coordinates. That form is only valid when Image "
            "Orientation (Patient) is [1, 0, 0, 0, 1, 0] and its first element "
            "matches the z value of Image Position (Patient) within "
            f"{_ABSOLUTE_OFFSET_TOLERANCE_MM} mm. Got orientation "
            f"{orientation.tolist()}, first offset {offsets[0]} and IPP z "
            f"{position[2]}."
        )

    relative_offsets: "np.ndarray" = offsets - position[2]
    return relative_offsets


@dataclass(frozen=True)
class _DoseGridGeometry:
    """Compact DICOM geometry, preserving the pixel array's dimension mapping.

    ``basis`` has columns ``(r, c, r x c)`` and ``local_axes`` contains column,
    row and slice displacements in mm. The standard's voxel transformation is
    ``position + encoded_basis @ [column_mm, row_mm, slice_offset_mm]``. Slice offsets
    need not be uniform, so the third input is a displacement, not an index.

    ``basis`` is snapped to a signed permutation for axis extraction;
    ``encoded_basis`` retains the file's cosines for physical comparisons.
    Only signed axis permutations are supported here. Their patient axes can
    be extracted in O(columns + rows + slices), without a coordinate volume.
    """

    position: "np.ndarray"
    basis: "np.ndarray"
    local_axes: Tuple["np.ndarray", "np.ndarray", "np.ndarray"]
    encoded_basis: "np.ndarray"

    @classmethod
    def from_dataset(cls, ds):
        position = np.array(ds.ImagePositionPatient, dtype=np.float64)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError("ImagePositionPatient must contain three finite values")

        orientation = _axis_aligned_orientation(ds)
        row, column = orientation[:3], orientation[3:]
        basis = np.column_stack((row, column, np.cross(row, column)))

        # Retain the encoded cosines for physical equality comparisons. Snapping
        # to cardinal axes is an approximation and can hide a growing edge error.
        encoded = np.array(ds.ImageOrientationPatient, dtype=np.float64)
        encoded_basis = np.column_stack(
            (encoded[:3], encoded[3:], np.cross(encoded[:3], encoded[3:]))
        )

        spacing = np.array(ds.PixelSpacing, dtype=np.float64)
        sizes = np.array((ds.Rows, ds.Columns))
        if (
            spacing.shape != (2,)
            or not np.all(np.isfinite(spacing))
            or np.any(sizes < 1)
            or np.any(spacing < 0)
            or np.any((spacing == 0) & (sizes > 1))
        ):
            raise ValueError(
                "PixelSpacing must contain finite positive row and column spacings "
                "(zero is allowed only for a singleton dimension)"
            )

        return cls(
            position,
            basis,
            (
                np.arange(ds.Columns, dtype=np.float64) * spacing[1],
                np.arange(ds.Rows, dtype=np.float64) * spacing[0],
                _slice_offsets(ds, position, orientation),
            ),
            encoded_basis,
        )

    @property
    def xyz_to_pixel_dimensions(self):
        """Pixel array dimension corresponding to each patient x, y, z axis."""
        return tuple(2 - int(index) for index in np.argmax(np.abs(self.basis), axis=1))

    def dicom_axes(self):
        return tuple(
            self.position[dimension]
            + self.basis[dimension, 2 - pixel_dimension]
            * self.local_axes[2 - pixel_dimension]
            for dimension, pixel_dimension in enumerate(self.xyz_to_pixel_dimensions)
        )

    def fixed_axes(self):
        # Preserve the legacy image-aligned IEC FIXED convention.
        origin = self.position @ self.basis
        columns, rows, slices = self.local_axes
        return origin[0] + columns, origin[2] + slices, -(origin[1] + rows)[::-1]

    def maximum_voxel_displacement(self, other):
        """Largest encoded 3D displacement, or infinity for incompatible mappings.

        Within each slice the difference is affine in row and column. Its norm
        is convex, so its maximum occurs at an in-plane corner. Check all four
        corners of every slice: uneven offset errors can peak on an inner slice.
        This uses O(slices) memory, including for slightly rounded orientations.
        """
        if not np.array_equal(self.basis, other.basis) or any(
            left.shape != right.shape
            for left, right in zip(self.local_axes, other.local_axes)
        ):
            return np.inf

        # Subtract the origins first to avoid cancellation from adding a large
        # common patient coordinate to every voxel before taking differences.
        slice_deltas = (
            (self.position - other.position)
            + self.local_axes[2][:, None] * self.encoded_basis[:, 2]
            - other.local_axes[2][:, None] * other.encoded_basis[:, 2]
        )
        maximum = 0.0
        for column in (0, -1):
            for row in (0, -1):
                displacement = slice_deltas.copy()
                for dimension, index in ((0, column), (1, row)):
                    displacement += (
                        self.local_axes[dimension][index]
                        * self.encoded_basis[:, dimension]
                        - other.local_axes[dimension][index]
                        * other.encoded_basis[:, dimension]
                    )
                maximum = max(
                    maximum, float(np.max(np.linalg.norm(displacement, axis=1)))
                )
        return maximum

    def matches_pixel_mapping(self, other):
        """Apply the physical acceptance limits to corresponding voxel centres."""
        return _displacement_is_acceptable(self.maximum_voxel_displacement(other))


def _displacement_is_acceptable(displacement):
    if displacement > _COORDINATE_ACCEPTANCE_TOLERANCE_MM + _NUMERICAL_TOLERANCE_MM:
        return False
    if displacement > _COORDINATE_QUIET_TOLERANCE_MM + _NUMERICAL_TOLERANCE_MM:
        warnings.warn(
            f"Corresponding dose-grid voxel centres differ by up to {displacement:.6g} mm. "
            f"This exceeds the quiet tolerance of {_COORDINATE_QUIET_TOLERANCE_MM} mm "
            f"but is within the {_COORDINATE_ACCEPTANCE_TOLERANCE_MM} mm acceptance limit; "
            "the grids are treated as coincident without resampling. "
            "This geometric tolerance does not assess clinical significance.",
            UserWarning,
            stacklevel=3,
        )
    return True


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
        slices, and `x` and `y` follow the columns and rows respectively.
        For decubitus orientations the rows run along `x` and the columns
        along `y`. An axis is descending wherever the scanner stored the
        pixels in descending order (for example `x` for head first prone),
        with the dimension mapping described above. Use
        :func:`pymedphys.dicom.zyx_and_dose_from_dataset` for ascending
        axes with the dose reordered to match.

        For 'fixed', `x` follows the columns and `y` the slices, both in
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
    Supported transverse cardinal scan orientations [1]_. Direction cosines
    within 1e-4 are snapped to these directions for separable axis extraction;
    the positional effect of that approximation grows with grid extent.
    Grid-equality comparisons retain the original cosines.


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
    Each voxel's position follows PS3.3 C.7.6.2.1.1: for the voxel in slice
    ``k``, row ``row`` and column ``column``,
    ``IPP + column * PixelSpacing[1] * r + row * PixelSpacing[0] * c + offset[k] * n``,
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

    geometry = _DoseGridGeometry.from_dataset(ds)
    if system in ("FIXED", "IEC FIXED", "F"):
        axes = geometry.fixed_axes()
    else:
        axes = geometry.dicom_axes()

    x, y, z = axes
    return (
        np.ascontiguousarray(x, dtype=np.float64),
        np.ascontiguousarray(y, dtype=np.float64),
        np.ascontiguousarray(z, dtype=np.float64),
    )


def coords_in_datasets_are_equal(datasets: Sequence["pydicom.dataset.Dataset"]) -> bool:
    """True if matching pixel indices have matching DICOM coordinates.

    Equal patient-coordinate axes alone are insufficient: decubitus grids
    can have the same axes but a different row/column mapping. This check is
    used before adding raw pixel arrays, so their mappings must also agree.
    For every pair of datasets, corresponding voxel centres are compared using
    the original encoded direction cosines, including accepted rounding. The
    maximum Euclidean displacement is accepted silently through 0.01 mm, with
    a UserWarning above 0.01 mm through 0.1 mm, and rejected above 0.1 mm.
    Accepted grids are treated as coincident without resampling. These absolute
    physical limits do not depend on the coordinate origin and do not assess
    clinical significance. A separate 1e-9 mm allowance handles arithmetic
    round-off at the limits.

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

    geometries = [_DoseGridGeometry.from_dataset(ds) for ds in datasets]
    maximum = max(
        (
            left.maximum_voxel_displacement(right)
            for left, right in combinations(geometries, 2)
        ),
        default=0.0,
    )
    return _displacement_is_acceptable(maximum)
