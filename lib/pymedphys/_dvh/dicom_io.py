from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pydicom

# --- Geometry helpers for DICOM dose grid transforms ---


@dataclass
class DoseGridGeom:
    """Mapping between patient coords (mm) and dose grid indices (k, r, c)."""

    ipp: np.ndarray  # (3,)
    u: np.ndarray  # row direction cosines (3,)
    v: np.ndarray  # col direction cosines (3,)
    w: np.ndarray  # slice normal (3,) = cross(u,v)
    ps_row: float  # mm
    ps_col: float  # mm
    gfo: np.ndarray  # GridFrameOffsetVector (K,) in mm along w
    shape: Tuple[int, int, int]  # (K, R, C)

    def world_to_ijk(self, xyz: np.ndarray) -> np.ndarray:
        """
        Map patient coords (N,3) -> fractional dose indices (N,3) = (k, r, c).
        k is fractional through gfo; r along v; c along u.
        """
        delta = xyz - self.ipp[None, :]
        c = np.dot(delta, self.u) / self.ps_col
        r = np.dot(delta, self.v) / self.ps_row
        wdist = np.dot(delta, self.w)
        # Assume uniform gfo spacing; fall back to linear interpolation otherwise.
        if len(self.gfo) > 1:
            dz = self.gfo[1] - self.gfo[0]
            if np.allclose(self.gfo, self.gfo[0] + dz * np.arange(len(self.gfo))):
                k = (wdist - self.gfo[0]) / dz
            else:
                # Non-uniform; find fractional index via np.interp on cumulative
                k = np.interp(wdist, self.gfo, np.arange(len(self.gfo)))
        else:
            k = np.zeros_like(wdist)
        return np.stack([k, r, c], axis=-1)

    def ijk_to_world(self, ijk: np.ndarray) -> np.ndarray:
        """Map (N,3) indices -> patient coords (N,3)."""
        k, r, c = ijk[..., 0], ijk[..., 1], ijk[..., 2]
        p = (
            self.ipp[None, :]
            + np.outer(c, self.u) * self.ps_col
            + np.outer(r, self.v) * self.ps_row
            + np.outer(
                self.gfo[0]
                + k * (self.gfo[1] - self.gfo[0] if len(self.gfo) > 1 else 0.0),
                self.w,
            )
        )
        return p


def _read_orientation(ds) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    iop = np.array(ds.ImageOrientationPatient, dtype=float)  # [ux,uy,uz, vx,vy,vz]
    u = iop[:3] / np.linalg.norm(iop[:3])
    v = iop[3:] / np.linalg.norm(iop[3:])
    w = np.cross(u, v)
    w /= np.linalg.norm(w)
    return u, v, w


def read_rtdose(path: str) -> Tuple[np.ndarray, DoseGridGeom, float]:
    """
    Read DICOM RTDOSE into (dose_Gy[K,R,C], geom, scaling).
    """
    ds = pydicom.dcmread(path)
    assert ds.Modality == "RTDOSE"
    arr = ds.pixel_array.astype(np.float64)
    scale = float(ds.DoseGridScaling)
    dose = arr * scale  # Gy
    rows, cols = int(ds.Rows), int(ds.Columns)
    num_frames = int(ds.NumberOfFrames)
    dose = dose.reshape((num_frames, rows, cols))
    ipp = np.array(ds.ImagePositionPatient, dtype=float)
    u, v, w = _read_orientation(ds)
    ps_row, ps_col = [float(x) for x in ds.PixelSpacing]
    gfo = np.array(ds.GridFrameOffsetVector, dtype=float)
    geom = DoseGridGeom(
        ipp=ipp, u=u, v=v, w=w, ps_row=ps_row, ps_col=ps_col, gfo=gfo, shape=dose.shape
    )
    return dose, geom, scale


@dataclass
class Contour2D:
    z_mm: float
    points_rc: List[np.ndarray]  # list of (N_i, 2) arrays in (row, col) index space


@dataclass
class ROI:
    name: str
    number: int
    contours: List[Contour2D]  # sorted by z


def read_rtstruct_as_rois(rtstruct_path: str, dose_geom: DoseGridGeom) -> List[ROI]:
    """
    Parse RTSTRUCT and re-express all contours in DOSE grid (row, col) index coordinates.
    Assumes FrameOfReferenceUID matches between RTSTRUCT and RTDOSE.

    We do not require CT import for DVH, aligning with prior observations that DVH can
    be formed from dose+structure alone when FoRUID matches. :contentReference[oaicite:8]{index=8}
    """
    ds = pydicom.dcmread(rtstruct_path)
    assert ds.Modality == "RTSTRUCT"
    rois: Dict[int, ROI] = {}
    name_by_num = {
        int(roi.ROINumber): str(roi.ROIName) for roi in ds.StructureSetROISequence
    }
    for roi_cont in ds.ROIContourSequence:
        num = int(roi_cont.ReferencedROINumber)
        name = name_by_num.get(num, f"ROI_{num}")
        contours: Dict[float, List[np.ndarray]] = {}
        for cs in roi_cont.ContourSequence:
            pts = np.array(cs.ContourData, dtype=float).reshape((-1, 3))
            # Map to (k,r,c) and keep the (r,c); z_mm from world via w·(x-ipp)
            ijk = dose_geom.world_to_ijk(pts)
            rc = ijk[:, 1:3]  # (row, col)
            # Use the mean w-distance to represent this slice's z
            # recover wdist for first point:
            delta = pts[0] - dose_geom.ipp
            z_mm = float(np.dot(delta, dose_geom.w))
            contours.setdefault(z_mm, []).append(rc)
        # Pack
        c2d = [Contour2D(z, lst) for z, lst in contours.items()]
        c2d.sort(key=lambda c: c.z_mm)
        rois[num] = ROI(name=name, number=num, contours=c2d)
    return list(rois.values())
