"""Geometry / structure types (RFC section 6.7).

Validation covers structural correctness and orientation normalisation.
Full geometric validation (self-intersection, repeated vertices, hole
containment) is not yet implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._types._roi_ref import ROIRef
from pymedphys._dvh._types._validators import validate_finite_array


class CombinationMode(str, Enum):
    """How overlapping contours on the same slice are combined.

    AUTO
        Automatically detect the appropriate combination based on
        contour winding and overlap.
    UNION
        Combine all contours as a union (logical OR).
    XOR
        Combine contours using the even-odd rule (XOR).
    """

    AUTO = "auto"
    UNION = "union"
    XOR = "xor"


class CoordinateFrame(str, Enum):
    """Coordinate frame of contour data.

    DICOM_PATIENT
        DICOM patient coordinate system (IEC 61217 / DICOM C.7.6.2).
    """

    DICOM_PATIENT = "DICOM_PATIENT"


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
        validate_finite_array("Contour.points_xy", pts, ndim=2)
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


def _signed_area(pts: npt.NDArray[np.float64]) -> float:
    """Shoelace formula signed area. Positive = CCW, negative = CW."""
    x, y = pts[:, 0], pts[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


@dataclass(frozen=True, slots=True, eq=False)
class PlanarRegion:
    """A validated 2D region on a single slice: one exterior boundary
    with zero or more holes.

    The exterior must be CCW (positive signed area). Each hole must be
    CW (negative signed area).

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
        validate_finite_array("PlanarRegion.exterior_xy_mm", ext, ndim=2)
        # D7: Validate exterior is CCW (positive signed area)
        ext_area = _signed_area(ext)
        if ext_area <= 0:
            raise ValueError(
                f"PlanarRegion exterior must be CCW (positive area), "
                f"got signed area {ext_area:.6f}"
            )
        ext.flags.writeable = False
        object.__setattr__(self, "exterior_xy_mm", ext)

        validated_holes = []
        for i, h in enumerate(self.holes_xy_mm):
            hc = np.array(h, dtype=np.float64)
            validate_finite_array(f"PlanarRegion.holes_xy_mm[{i}]", hc, ndim=2)
            # D7: Validate each hole is CW (negative signed area)
            hole_area = _signed_area(hc)
            if hole_area >= 0:
                raise ValueError(
                    f"PlanarRegion hole {i} must be CW (negative area), "
                    f"got signed area {hole_area:.6f}"
                )
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
        return hash(
            (
                self.exterior_xy_mm.tobytes(),
                tuple(h.tobytes() for h in self.holes_xy_mm),
            )
        )


# C3: Type alias for a single contour slice
ContourSlice = tuple[float, tuple[PlanarRegion, ...]]
"""A single contour slice: ``(z_mm, regions)``."""


@dataclass(frozen=True, slots=True)
class ContourROI:
    """A validated, z-sorted ROI defined by planar regions on axial slices.

    Parameters
    ----------
    roi : ROIRef
        ROI identity.
    slices : tuple[ContourSlice, ...]
        ``(z_mm, regions)`` pairs, sorted ascending by z_mm.
    combination_mode : CombinationMode
        How overlapping contours on the same slice are combined.
    coordinate_frame : CoordinateFrame
        Coordinate frame of the contour data.
    """

    roi: ROIRef
    slices: tuple[ContourSlice, ...]
    combination_mode: CombinationMode = CombinationMode.AUTO
    coordinate_frame: CoordinateFrame = CoordinateFrame.DICOM_PATIENT

    def __post_init__(self) -> None:
        # Coerce strings to enum for backward compatibility
        if isinstance(self.combination_mode, str):
            object.__setattr__(
                self, "combination_mode", CombinationMode(self.combination_mode)
            )
        if isinstance(self.coordinate_frame, str):
            object.__setattr__(
                self, "coordinate_frame", CoordinateFrame(self.coordinate_frame)
            )
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
    def mean_slice_spacing_mm(self) -> float | None:
        """Mean spacing between slices, or None for single-slice ROI.

        For non-uniform slice spacing (common in DICOM exports), this
        returns the arithmetic mean of inter-slice gaps. Check
        ``is_uniform_spacing`` to determine if slices are evenly spaced.
        """
        if self.num_slices < 2:
            return None
        return self.z_extent_mm / (self.num_slices - 1)

    @property
    def slice_spacings_mm(self) -> tuple[float, ...] | None:
        """Individual inter-slice spacings, or None for single-slice ROI."""
        if self.num_slices < 2:
            return None
        zs = self.z_values_mm
        return tuple(zs[i + 1] - zs[i] for i in range(len(zs) - 1))

    @property
    def is_uniform_spacing(self) -> bool | None:
        """Whether slices are uniformly spaced (within 0.01 mm tolerance).

        Returns None for single-slice ROIs.
        """
        spacings = self.slice_spacings_mm
        if spacings is None:
            return None
        return all(abs(s - spacings[0]) < 0.01 for s in spacings)
