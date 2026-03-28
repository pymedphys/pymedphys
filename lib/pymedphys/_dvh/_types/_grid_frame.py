"""GridFrame — regular 3D grid in patient coordinates (RFC section 6.2)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._validators import _validate_finite_array


def _validate_axis_aligned_affine(aff: npt.NDArray[np.float64]) -> None:
    """Enforce v1 axis-aligned affine constraints.

    Parameters
    ----------
    aff : npt.NDArray[np.float64]
        4x4 affine matrix.

    Raises
    ------
    ValueError
        If the affine violates axis-aligned constraints: last row
        must be [0, 0, 0, 1], the 3x3 linear submatrix must have
        exactly one non-zero entry per column (axis-aligned, no shear),
        and axes must be orthogonal.
    """
    # Last row must be [0, 0, 0, 1]
    expected_last_row = np.array([0.0, 0.0, 0.0, 1.0])
    if not np.allclose(aff[3, :], expected_last_row):
        raise ValueError(
            f"Affine last row must be [0, 0, 0, 1], got {aff[3, :].tolist()}"
        )

    # Each column of the 3x3 linear part must have exactly one non-zero entry
    linear = aff[:3, :3]
    # Zero-out tiny numerical noise so that near-axis-aligned DICOM affines
    # are not rejected due to floating-point artefacts (e.g. 1e-15 from
    # DICOM header parsing).  Threshold 1e-8 is well below typical voxel
    # spacings (~0.1 mm) while above double-precision round-off (~1e-16).
    linear = np.where(np.abs(linear) < 1e-8, 0.0, linear)
    for col_idx in range(3):
        col = linear[:, col_idx]
        nonzero_count = np.count_nonzero(col)
        if nonzero_count != 1:
            raise ValueError(
                f"Affine column {col_idx} must have exactly one non-zero "
                f"spatial entry (axis-aligned), got {col.tolist()}"
            )

    # Each row of the 3x3 linear part must have exactly one non-zero entry
    # (ensures orthogonality with no shear)
    for row_idx in range(3):
        row = linear[row_idx, :]
        nonzero_count = np.count_nonzero(row)
        if nonzero_count != 1:
            raise ValueError(
                f"Affine row {row_idx} must have exactly one non-zero "
                f"spatial entry (no shear), got {row.tolist()}"
            )


@dataclass(frozen=True, slots=True, eq=False)
class GridFrame:
    """Defines a regular 3D grid in patient coordinates with an explicit
    index-to-patient affine transform.

    The canonical array axis order is (z, y, x) — matching the DICOM
    convention where the z-axis (slice direction) is the slowest-varying
    index. All 3D arrays in the system (dose, occupancy, SDF) use this
    axis order.

    The affine transform ``index_to_patient_mm`` is a 4x4 matrix mapping
    integer voxel indices (iz, iy, ix) to patient coordinates (x, y, z)
    in mm.

    v1 restriction: axis-aligned grids only. The affine must have
    orthogonal axes with exactly one non-zero spatial term per index
    axis (no shear, no rotation other than axis permutation), and
    the last row must be ``[0, 0, 0, 1]``.

    Parameters
    ----------
    shape_zyx : tuple[int, int, int]
        Grid dimensions (nz, ny, nx). All must be strictly positive.
    index_to_patient_mm : npt.NDArray[np.float64]
        4x4 affine matrix mapping voxel indices to patient mm.
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
        _validate_finite_array(aff, "index_to_patient_mm")
        _validate_axis_aligned_affine(aff)
        aff.flags.writeable = False
        object.__setattr__(self, "index_to_patient_mm", aff)

        sp = self.spacing_mm
        if any(s <= 0 for s in sp):
            raise ValueError(f"Derived spacing must be positive, got {sp}")

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
        spacing_xyz_mm: tuple[float, float, float],
        origin_xyz_mm: tuple[float, float, float],
    ) -> GridFrame:
        """Convenience constructor for axis-aligned uniform grids.

        Parameters
        ----------
        shape_zyx : tuple[int, int, int]
            (nz, ny, nx) grid dimensions.
        spacing_xyz_mm : tuple[float, float, float]
            (dx, dy, dz) voxel spacing in mm.
        origin_xyz_mm : tuple[float, float, float]
            (x, y, z) of voxel [0, 0, 0] centre in mm.
        """
        dx, dy, dz = spacing_xyz_mm
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
            shape_zyx=tuple(d["shape_zyx"]),
            index_to_patient_mm=np.array(d["index_to_patient_mm"], dtype=np.float64),
        )
