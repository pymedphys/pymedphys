# pymedphys/_dvh/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "DoseGrid",
    "StructureContour",
    "Structure3D",
    "ImageVolume",
    "DicomStudy",
]

FloatArray = NDArray[np.floating]
IntArray = NDArray[np.integer]


@dataclass(slots=True)
class DoseGrid:
    """
    A 3D dose grid and its geometry in DICOM patient coordinates (LPS, millimetres).

    Conventions
    -----------
    - `values` are **in Gy**, shaped (nz, ny, nx) == (frames, rows, cols).
    - Geometry is defined by DICOM attributes: ImagePositionPatient (IPP),
      ImageOrientationPatient (IOP), PixelSpacing (PS), and GridFrameOffsetVector (GFOv).
    - Orientation matrix columns are the DICOM row, column, and slice-normal direction cosines.
      world = IPP + (x*dx)*row_dir + (y*dy)*col_dir + (offsets[z])*normal_dir

    Notes
    -----
    DICOM defines IPP as the position of the *first transmitted pixel* (0,0) centre of frame 0.
    We therefore treat (z=0, y=0, x=0) as the voxel centre at IPP. This keeps index→world
    mapping simple and is adequate for DVH purposes.
    """

    values: FloatArray  # Gy, shape (nz, ny, nx)
    origin_ipp_mm: FloatArray  # (3,)
    orientation_matrix: FloatArray  # (3, 3) columns = (row, col, normal)
    spacing_mm: Tuple[float, float, float]  # (dx, dy, dz) in mm
    frame_offsets_mm: FloatArray  # (nz,), offsets along normal from frame 0 plane
    dose_units: str = "GY"
    frame_of_reference_uid: Optional[str] = None
    sop_instance_uid: Optional[str] = None

    def __post_init__(self) -> None:
        if self.values.ndim != 3:
            raise ValueError("DoseGrid.values must be 3D (nz, ny, nx).")
        if self.origin_ipp_mm.shape != (3,):
            raise ValueError("origin_ipp_mm must be a length-3 vector.")
        if self.orientation_matrix.shape != (3, 3):
            raise ValueError("orientation_matrix must be shape (3, 3).")
        if len(self.spacing_mm) != 3:
            raise ValueError("spacing_mm must be a 3-tuple (dx, dy, dz).")
        if self.frame_offsets_mm.shape != (self.values.shape[0],):
            raise ValueError("frame_offsets_mm length must equal nz (NumberOfFrames).")

    @property
    def shape(self) -> Tuple[int, int, int]:
        """Return (nz, ny, nx)."""
        return self.values.shape

    @property
    def dtype(self):
        return self.values.dtype

    @property
    def row_dir(self) -> FloatArray:
        """Direction cosines of DICOM 'row' axis (unit vector)."""
        return self.orientation_matrix[:, 0]

    @property
    def col_dir(self) -> FloatArray:
        """Direction cosines of DICOM 'column' axis (unit vector)."""
        return self.orientation_matrix[:, 1]

    @property
    def normal_dir(self) -> FloatArray:
        """Direction cosines of slice-normal axis (unit vector)."""
        return self.orientation_matrix[:, 2]

    def frame_origin(self, z: int) -> FloatArray:
        """
        World coordinates (mm, LPS) of the (0,0) voxel centre for frame z.
        """
        return self.origin_ipp_mm + self.frame_offsets_mm[z] * self.normal_dir

    def index_to_world(self, z: int, y: int, x: int) -> FloatArray:
        """
        Map voxel indices (z, y, x) → world mm (LPS).

        Parameters
        ----------
        z, y, x : int
            Index of frame, row, and column respectively (0-based).

        Returns
        -------
        ndarray, shape (3,)
            World coordinate in mm (LPS).
        """
        dx, dy, _ = self.spacing_mm
        return self.frame_origin(z) + (x * dx) * self.row_dir + (y * dy) * self.col_dir

    def world_to_index(self, xyz_mm: Sequence[float]) -> Tuple[float, float, float]:
        """
        Project a world coordinate (mm, LPS) into fractional grid index space (z, y, x).

        Notes
        -----
        Returns fractional indices; caller may round/floor as appropriate.
        """
        p = np.asarray(xyz_mm, dtype=float)
        v = p - self.origin_ipp_mm

        # Project onto orientation axes
        rz = float(np.dot(v, self.normal_dir))
        ry = float(np.dot(v, self.col_dir))
        rx = float(np.dot(v, self.row_dir))

        # z is found by locating nearest frame offset
        z = float(np.interp(rz, self.frame_offsets_mm, np.arange(self.shape[0])))
        dx, dy, _dz = self.spacing_mm
        y = ry / dy
        x = rx / dx
        return (z, y, x)

    def volume_mm3(self) -> float:
        """Total physical volume of the grid (axis-aligned bounding prism), mm³."""
        dzs = np.diff(self.frame_offsets_mm)
        dz = float(np.mean(np.abs(dzs))) if len(dzs) else self.spacing_mm[2]
        nx = self.shape[2]
        ny = self.shape[1]
        dx, dy, _ = self.spacing_mm
        return float(nx * dx * ny * dy * self.shape[0] * dz)

    def corners_world(self) -> FloatArray:
        """
        World coordinates of the 8 outer voxel corners (approximate) for bounding-box checks.

        Returns
        -------
        ndarray, shape (8, 3)
        """
        nz, ny, nx = self.shape
        dx, dy, _dz = self.spacing_mm
        corners = []
        for z in (0, nz - 1):
            origin = self.frame_origin(z)
            for y in (0, ny - 1):
                for x in (0, nx - 1):
                    p = origin + (x * dx) * self.row_dir + (y * dy) * self.col_dir
                    corners.append(p)
        return np.vstack(corners)


@dataclass(slots=True)
class StructureContour:
    """
    A single closed planar contour (a 'ring') belonging to a structure on one axial plane.

    Attributes
    ----------
    points_mm : (N, 3) float array
        Consecutive 3D points (mm, LPS). Last point need not repeat the first.
    is_hole : bool
        If True, treat as a hole (exclusion) when performing in-slice inclusion logic.
        For general DVH usage this is advisory metadata computed from signed area.
    """

    points_mm: FloatArray
    is_hole: bool = False

    def __post_init__(self) -> None:
        if self.points_mm.ndim != 2 or self.points_mm.shape[1] != 3:
            raise ValueError("points_mm must have shape (N, 3).")

    @property
    def z_mm(self) -> float:
        return float(np.mean(self.points_mm[:, 2]))

    @staticmethod
    def _signed_area_xy(points: FloatArray) -> float:
        """Signed area of polygon projected into XY; positive = CCW."""
        x = points[:, 0]
        y = points[:, 1]
        return 0.5 * float(np.sum(x * np.roll(y, -1) - y * np.roll(x, -1)))

    @classmethod
    def from_points(cls, pts_mm: FloatArray) -> "StructureContour":
        pts = np.asarray(pts_mm, dtype=float)
        area = cls._signed_area_xy(pts)
        is_hole = bool(area < 0.0)
        return cls(points_mm=pts, is_hole=is_hole)


@dataclass(slots=True)
class Structure3D:
    """
    A volumetric structure described as a set of closed contours per axial plane.

    Attributes
    ----------
    name : str
        Human-friendly name (e.g., 'PTV_66').
    number : int
        ROI number from the DICOM RTSTRUCT.
    planes : dict[z_mm -> list[StructureContour]]
        Mapping from axial plane position (mm) to a list of rings (outer + holes).
    frame_of_reference_uid : Optional[str]
        DICOM FrameOfReferenceUID, when available.

    Notes
    -----
    - DVH engines will voxelise these rings (with holes) using an inclusion rule (even-odd or winding).
    - We do not assume contour winding is consistent across vendors; `is_hole` is computed per ring.
    """

    name: str
    number: int
    planes: Dict[float, List[StructureContour]] = field(default_factory=dict)
    frame_of_reference_uid: Optional[str] = None

    def plane_zs(self) -> List[float]:
        zs = list(self.planes.keys())
        zs.sort()
        return zs

    def num_contours(self) -> int:
        return sum(len(rings) for rings in self.planes.values())

    def add_ring(self, z_mm: float, ring: StructureContour) -> None:
        self.planes.setdefault(z_mm, []).append(ring)

    def bounding_box_mm(self) -> Tuple[FloatArray, FloatArray]:
        """Axis-aligned bounding box as (min_xyz, max_xyz), mm."""
        pts = (
            np.vstack([r.points_mm for rings in self.planes.values() for r in rings])
            if self.planes
            else np.zeros((0, 3))
        )
        if pts.size == 0:
            return np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])
        return np.min(pts, axis=0), np.max(pts, axis=0)


@dataclass(slots=True)
class ImageVolume:
    """
    Minimal CT series geometry needed for DVH tasks (no pixel data required).

    Attributes
    ----------
    origin_ipp_mm : (3,) float array
        IPP of the first slice.
    orientation_matrix : (3, 3) float array
        Columns = (row, col, normal) direction cosines.
    pixel_spacing_mm : (dy, dx) tuple
        DICOM PixelSpacing (row, col) in mm.
    slice_positions_mm : (nz,) float array
        Positions along the slice normal (mm) relative to first slice.
    frame_of_reference_uid : Optional[str]
        FrameOfReferenceUID for cross-object sanity checks.
    """

    origin_ipp_mm: FloatArray
    orientation_matrix: FloatArray
    pixel_spacing_mm: Tuple[float, float]
    slice_positions_mm: FloatArray
    frame_of_reference_uid: Optional[str] = None

    @property
    def nz(self) -> int:
        return int(self.slice_positions_mm.size)


@dataclass(slots=True)
class DicomStudy:
    """
    A lightweight container bundling the dose and structures (and optional CT) for DVH computation.
    """

    dose: DoseGrid
    structures: Dict[str, Structure3D]
    ct: Optional[ImageVolume] = None
