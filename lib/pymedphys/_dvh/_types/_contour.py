"""Geometry / structure types (RFC section 6.7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._roi_ref import ROIRef


@dataclass(frozen=True, slots=True, eq=False)
class Contour:
    """A single closed 2D polygon on a single axial slice.

    Points are stored as an (N, 2) array of (x, y) coordinates in mm.
    This is a raw contour — it may have any winding order and may
    contain defects. Use ``PlanarRegion`` for validated geometry.

    Parameters
    ----------
    points_xy : npt.NDArray[np.float64]
        Shape (N, 2) with N >= 3.
    z_mm : float
        Axial slice position in mm. Must be finite.
    """

    points_xy: npt.NDArray[np.float64]
    z_mm: float

    def __post_init__(self) -> None:
        if self.points_xy.ndim != 2 or self.points_xy.shape[1] != 2:
            raise ValueError(f"Expected (N, 2) array, got shape {self.points_xy.shape}")
        if self.points_xy.shape[0] < 3:
            raise ValueError(
                f"Contour needs >= 3 points, got {self.points_xy.shape[0]}"
            )
        if not np.isfinite(self.z_mm):
            raise ValueError(f"z_mm must be finite, got {self.z_mm}")
        pts = np.array(self.points_xy, dtype=np.float64)
        pts.flags.writeable = False
        object.__setattr__(self, "points_xy", pts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contour):
            return NotImplemented
        return self.z_mm == other.z_mm and np.array_equal(
            self.points_xy, other.points_xy
        )

    def __hash__(self) -> int:
        return hash((self.z_mm, self.points_xy.tobytes()))


@dataclass(frozen=True, slots=True, eq=False)
class PlanarRegion:
    """A validated 2D region on a single slice: one exterior boundary
    with zero or more holes.

    The exterior is CCW (positive signed area). Each hole is CW
    (negative signed area).

    Parameters
    ----------
    exterior_xy_mm : npt.NDArray[np.float64]
        (N, 2) exterior boundary, CCW.
    holes_xy_mm : tuple[npt.NDArray[np.float64], ...]
        Each hole as (M, 2) array, CW.
    """

    exterior_xy_mm: npt.NDArray[np.float64]
    holes_xy_mm: tuple[npt.NDArray[np.float64], ...] = ()

    def __post_init__(self) -> None:
        ext = np.array(self.exterior_xy_mm, dtype=np.float64)
        ext.flags.writeable = False
        object.__setattr__(self, "exterior_xy_mm", ext)

        validated_holes = []
        for h in self.holes_xy_mm:
            hc = np.array(h, dtype=np.float64)
            hc.flags.writeable = False
            validated_holes.append(hc)
        object.__setattr__(self, "holes_xy_mm", tuple(validated_holes))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlanarRegion):
            return NotImplemented
        if not np.array_equal(self.exterior_xy_mm, other.exterior_xy_mm):
            return False
        if len(self.holes_xy_mm) != len(other.holes_xy_mm):
            return False
        return all(
            np.array_equal(a, b) for a, b in zip(self.holes_xy_mm, other.holes_xy_mm)
        )

    def __hash__(self) -> int:
        return hash(self.exterior_xy_mm.tobytes())


@dataclass(frozen=True, slots=True)
class ContourROI:
    """A validated, z-sorted ROI defined by planar regions on axial slices.

    Parameters
    ----------
    roi : ROIRef
        ROI identity.
    slices : tuple[tuple[float, tuple[PlanarRegion, ...]], ...]
        (z_mm, regions) pairs, sorted ascending by z_mm.
    combination_mode : str
        How overlapping contours on the same slice are combined.
    coordinate_frame : str
        Coordinate frame of the contour data.
    """

    roi: ROIRef
    slices: tuple[tuple[float, tuple[PlanarRegion, ...]], ...]
    combination_mode: str = "auto"
    coordinate_frame: str = "DICOM_PATIENT"

    def __post_init__(self) -> None:
        if not self.slices:
            raise ValueError(f"ContourROI '{self.roi}' has no slices")
        z_values = [s[0] for s in self.slices]
        if z_values != sorted(z_values):
            raise ValueError(f"Slices not sorted by z for '{self.roi}'")
        if len(z_values) != len(set(z_values)):
            raise ValueError(f"Duplicate z values in '{self.roi}'")
        for z, regions in self.slices:
            if not regions:
                raise ValueError(f"Empty slice at z={z} in '{self.roi}'")

    @property
    def num_slices(self) -> int:
        """Number of contour slices."""
        return len(self.slices)

    @property
    def z_values_mm(self) -> tuple[float, ...]:
        """Z positions of all slices."""
        return tuple(s[0] for s in self.slices)

    @property
    def z_extent_mm(self) -> float:
        """Total z extent (last z - first z)."""
        zs = self.z_values_mm
        return zs[-1] - zs[0]

    @property
    def mean_slice_spacing_mm(self) -> Optional[float]:
        """Mean spacing between slices, or None for single-slice ROI."""
        if self.num_slices < 2:
            return None
        return self.z_extent_mm / (self.num_slices - 1)
