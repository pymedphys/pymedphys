"""GridFrame — regular 3D grid in patient coordinates (RFC section 6.2).

This implementation currently supports **axis-aligned grids only**, which
covers all standard DICOM RTDOSE grids. Non-axis-aligned (tilted) grids
may be supported in a future phase.

DICOM construction notes
------------------------
When constructing a ``GridFrame`` from DICOM RTDOSE, the affine maps
voxel indices ``(iz, iy, ix)`` to patient coordinates ``(x, y, z)`` in mm.
For a standard HFS RTDOSE with ``ImageOrientationPatient = [1,0,0,0,1,0]``:

.. code-block:: python

    # dx = PixelSpacing[1], dy = PixelSpacing[0], dz = GridFrameOffsetVector spacing
    # origin = ImagePositionPatient
    gf = GridFrame.from_uniform(
        shape_zyx=(nz, ny, nx),
        spacing_mm_xyz=(dx, dy, dz),
        origin_xyz_mm=(origin_x, origin_y, origin_z),
    )

The affine columns are ordered ``[iz_step | iy_step | ix_step | origin]``
which maps the ``(iz, iy, ix)`` index tuple to ``(x, y, z)`` patient mm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._validators import validate_finite_array


@dataclass(frozen=True, slots=True, eq=False)
class GridFrame:
    """Defines a regular, **axis-aligned** 3D grid in patient coordinates
    with an explicit index-to-patient affine transform.

    The canonical array axis order is ``(z, y, x)`` — matching the DICOM
    convention where the z-axis (slice direction) is the slowest-varying
    index. All 3D arrays in the system (dose, occupancy, SDF) use this
    axis order.

    The affine transform ``index_to_patient_mm`` is a 4×4 matrix mapping
    integer voxel indices ``(iz, iy, ix)`` to patient coordinates
    ``(x, y, z)`` in mm. Only axis-aligned affines are currently
    supported (off-diagonal elements of the 3×3 rotation sub-matrix
    must be zero).

    Parameters
    ----------
    shape_zyx : tuple[int, int, int]
        Grid dimensions ``(nz, ny, nx)``. All must be strictly positive.
    index_to_patient_mm : npt.NDArray[np.float64]
        4×4 affine matrix mapping voxel indices to patient mm.
        Must be axis-aligned (no off-diagonal rotation terms).
    """

    shape_zyx: tuple[int, int, int]
    index_to_patient_mm: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        if any(n <= 0 for n in self.shape_zyx):
            raise ValueError(f"Grid shape must be positive, got {self.shape_zyx}")
        if self.index_to_patient_mm.shape != (4, 4):
            raise ValueError(
                f"Affine must be (4, 4), got {self.index_to_patient_mm.shape}"
            )
        aff = np.array(self.index_to_patient_mm, dtype=np.float64)
        validate_finite_array("index_to_patient_mm", aff)

        # Validate bottom row is [0, 0, 0, 1]
        if not np.allclose(aff[3, :], [0, 0, 0, 1]):
            raise ValueError(
                f"Bottom row of affine must be [0, 0, 0, 1], got {aff[3, :]}"
            )

        # Check spacing is positive (before axis-alignment check, since
        # zero spacing would make the rotation matrix singular)
        col_norms = tuple(float(np.linalg.norm(aff[:3, i])) for i in range(3))
        if any(s <= 0 for s in col_norms):
            raise ValueError(
                f"Derived spacing must be positive, got "
                f"(dz={col_norms[0]}, dy={col_norms[1]}, dx={col_norms[2]})"
            )

        # Validate axis-aligned with fixed semantic mapping:
        #   column 0 (iz) -> patient z (row 2)
        #   column 1 (iy) -> patient y (row 1)
        #   column 2 (ix) -> patient x (row 0)
        # Sign flips are allowed; axis permutation is not.
        rot = aff[:3, :3]
        mask = np.abs(rot) > 1e-12

        # First check basic axis-alignment: one nonzero per row/column
        for i in range(3):
            if np.count_nonzero(mask[i, :]) != 1:
                raise ValueError(
                    "Only axis-aligned grids are currently supported. "
                    f"Row {i} of the affine rotation sub-matrix has "
                    f"multiple non-zero entries: {rot[i, :]}"
                )
            if np.count_nonzero(mask[:, i]) != 1:
                raise ValueError(
                    "Only axis-aligned grids are currently supported. "
                    f"Column {i} of the affine rotation sub-matrix has "
                    f"multiple non-zero entries: {rot[:, i]}"
                )

        # Enforce fixed axis semantics (no permutation):
        # col 0 (iz step) must have its nonzero in row 2 (patient z)
        # col 1 (iy step) must have its nonzero in row 1 (patient y)
        # col 2 (ix step) must have its nonzero in row 0 (patient x)
        expected_rows = {0: 2, 1: 1, 2: 0}  # col -> expected row
        for col, expected_row in expected_rows.items():
            # Safe: prior loop guarantees exactly one True per column
            nonzero_row = int(np.argmax(mask[:, col]))
            if nonzero_row != expected_row:
                axis_names = {0: "x", 1: "y", 2: "z"}
                idx_names = {0: "iz", 1: "iy", 2: "ix"}
                raise ValueError(
                    f"Axis permutation not allowed: column {col} "
                    f"({idx_names[col]}) must map to patient "
                    f"{axis_names[expected_row]}, but maps to patient "
                    f"{axis_names[nonzero_row]}. "
                    f"Use from_uniform() to construct standard grids."
                )

        aff.flags.writeable = False
        object.__setattr__(self, "index_to_patient_mm", aff)

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        """(dz, dy, dx) voxel spacing in mm, derived from the affine."""
        aff = self.index_to_patient_mm
        dz = float(np.linalg.norm(aff[:3, 0]))
        dy = float(np.linalg.norm(aff[:3, 1]))
        dx = float(np.linalg.norm(aff[:3, 2]))
        return (dz, dy, dx)

    @property
    def spacing_xyz_mm(self) -> tuple[float, float, float]:
        """(dx, dy, dz) spacing — patient-coordinate order convenience."""
        dz, dy, dx = self.spacing_mm
        return (dx, dy, dz)

    @property
    def origin_mm(self) -> tuple[float, float, float]:
        """(x, y, z) patient coordinate of voxel [0, 0, 0]."""
        aff = self.index_to_patient_mm
        return (float(aff[0, 3]), float(aff[1, 3]), float(aff[2, 3]))

    @property
    def num_voxels(self) -> int:
        """Total number of voxels in the grid."""
        return self.shape_zyx[0] * self.shape_zyx[1] * self.shape_zyx[2]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GridFrame):
            return NotImplemented
        return self.shape_zyx == other.shape_zyx and np.array_equal(
            self.index_to_patient_mm, other.index_to_patient_mm
        )

    def __hash__(self) -> int:
        return hash((self.shape_zyx, self.index_to_patient_mm.tobytes()))

    @classmethod
    def from_uniform(
        cls,
        shape_zyx: tuple[int, int, int],
        spacing_mm_xyz: tuple[float, float, float],
        origin_xyz_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> GridFrame:
        """Convenience constructor for axis-aligned uniform grids.

        Parameters
        ----------
        shape_zyx : tuple[int, int, int]
            ``(nz, ny, nx)`` grid dimensions.
        spacing_mm_xyz : tuple[float, float, float]
            ``(dx, dy, dz)`` voxel spacing in mm, in patient-coordinate
            (x, y, z) order.
        origin_xyz_mm : tuple[float, float, float]
            ``(x, y, z)`` of voxel ``[0, 0, 0]`` centre in mm.
        """
        dx, dy, dz = spacing_mm_xyz
        ox, oy, oz = origin_xyz_mm
        aff = np.array(
            [
                [0, 0, dx, ox],
                [0, dy, 0, oy],
                [dz, 0, 0, oz],
                [0, 0, 0, 1],
            ],
            dtype=np.float64,
        )
        return cls(shape_zyx=shape_zyx, index_to_patient_mm=aff)

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        return {
            "shape_zyx": list(self.shape_zyx),
            "index_to_patient_mm": self.index_to_patient_mm.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> GridFrame:
        """Deserialise from a plain dict."""
        return cls(
            shape_zyx=tuple(int(v) for v in d["shape_zyx"]),  # type: ignore[arg-type]
            index_to_patient_mm=np.array(d["index_to_patient_mm"], dtype=np.float64),
        )
