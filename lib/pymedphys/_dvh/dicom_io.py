# lib/pymedphys/_dvh/dicom_io.py
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pydicom

# --- Geometry helpers for DICOM dose grid transforms ---


@dataclass
class DoseGridGeom:
    """Mapping between patient coords (mm) and dose grid indices (k, r, c)."""

    ipp: np.ndarray  # (3,)
    u: np.ndarray  # ROW direction cosines (3,)
    v: np.ndarray  # COLUMN direction cosines (3,)
    w: np.ndarray  # SLICE normal (3,) = cross(u,v)
    ps_row: float  # mm (row pixel spacing: along u)
    ps_col: float  # mm (column pixel spacing: along v)
    gfo: np.ndarray  # GridFrameOffsetVector (K,) in mm along w
    shape: Tuple[int, int, int]  # (K, R, C)

    def world_to_ijk(self, xyz: np.ndarray) -> np.ndarray:
        """Map patient coords (N,3) -> fractional dose indices (N,3) = (k, r, c).

        r increases along ROW vector u with spacing ps_row
        c increases along COL vector v with spacing ps_col
        k increases along SLICE normal w following gfo offsets
        """
        delta = xyz - self.ipp[None, :]

        # row/col mapping (note: DICOM IOP = [row-dir, col-dir])
        r = np.dot(delta, self.u) / self.ps_row
        c = np.dot(delta, self.v) / self.ps_col

        # distance along slice normal
        wdist = np.dot(delta, self.w)

        # k from gfo
        if len(self.gfo) > 1:
            dz = self.gfo[1] - self.gfo[0]
            if np.allclose(self.gfo, self.gfo[0] + dz * np.arange(len(self.gfo))):
                k = (wdist - self.gfo[0]) / dz
            else:
                # Non‑uniform; find fractional index via interpolation
                k = np.interp(wdist, self.gfo, np.arange(len(self.gfo)))
        else:
            k = np.zeros_like(wdist)

        return np.stack([k, r, c], axis=-1)

    def ijk_to_world(self, ijk: np.ndarray) -> np.ndarray:
        """Map (N,3) indices -> patient coords (N,3)."""
        ijk = np.asarray(ijk, dtype=float)
        k, r, c = ijk[..., 0], ijk[..., 1], ijk[..., 2]

        # Piecewise‑linear w‑distance for possibly non‑uniform GFO
        if len(self.gfo) > 1:
            k0 = np.floor(k).astype(int)
            t = k - k0

            k0 = np.clip(k0, 0, len(self.gfo) - 2)
            g0 = self.gfo[k0]
            g1 = self.gfo[k0 + 1]
            wdist = (1.0 - t) * g0 + t * g1
        else:
            wdist = np.zeros_like(k) + self.gfo[0]

        # Compose patient coordinates
        p = (
            self.ipp[None, :]
            + np.outer(r, self.u) * self.ps_row
            + np.outer(c, self.v) * self.ps_col
            + np.outer(wdist, self.w)
        )
        return p


def _read_orientation(ds) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    iop = np.array(ds.ImageOrientationPatient, dtype=float)  # [ux,uy,uz, vx,vy,vz]
    u = iop[:3] / np.linalg.norm(iop[:3])  # row vector
    v = iop[3:] / np.linalg.norm(iop[3:])  # col vector
    w = np.cross(u, v)
    w /= np.linalg.norm(w)
    return u, v, w


def read_rtdose(path: str) -> Tuple[np.ndarray, DoseGridGeom, float]:
    """Read DICOM RTDOSE into (dose_Gy[K,R,C], geom, scaling)."""
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
        ipp=ipp,
        u=u,
        v=v,
        w=w,
        ps_row=ps_row,
        ps_col=ps_col,
        gfo=gfo,
        shape=dose.shape,
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
    We do not require CT import for DVH (dose+structure is sufficient when FoRUID matches).
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

            # Map to (k,r,c) and keep the (r,c)
            ijk = dose_geom.world_to_ijk(pts)
            rc = ijk[:, 1:3]  # (row, col)

            # Determine this contour's plane position along w using the MEAN of all points
            delta = pts - dose_geom.ipp[None, :]
            wdist_all = np.dot(delta, dose_geom.w)
            z_mm = float(np.mean(wdist_all))

            # Warn if points are not co-planar within tolerance (e.g. RTSTRUCT anomalies)
            z_spread = float(np.max(wdist_all) - np.min(wdist_all))
            if z_spread > 0.2:  # mm
                warnings.warn(
                    f"ROI '{name}': non‑planar contour points detected at nominal z={z_mm:.3f} mm "
                    f"(spread {z_spread:.3f} mm). Using mean plane for voxelisation."
                )

            contours.setdefault(z_mm, []).append(rc)

        # Pack and sort
        c2d = [Contour2D(z, lst) for z, lst in contours.items()]
        c2d.sort(key=lambda c: c.z_mm)
        rois[num] = ROI(name=name, number=num, contours=c2d)

    return list(rois.values())
