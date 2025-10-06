from __future__ import annotations

import warnings
from typing import Iterable, List

import numpy as np

from ..config import DVHConfig
from ..dicom_geom import DoseGridGeom
from ..dicom_io import ROI, Contour2D  # assumes you already have these dataclasses


def _points_in_ring_evenodd(
    px: np.ndarray, py: np.ndarray, ring_rc: np.ndarray
) -> np.ndarray:
    """Ray casting test for a single ring (returns boolean mask for points inside the ring)."""
    ring = np.asarray(ring_rc, dtype=float)
    if ring.ndim != 2 or ring.shape[1] != 2:
        raise ValueError("ring must be (M,2) [row, col]")

    # Use x=col, y=row
    x = ring[:, 1]
    y = ring[:, 0]
    # Ensure closed ring
    if not (np.isclose(x[0], x[-1]) and np.isclose(y[0], y[-1])):
        x = np.concatenate([x, x[:1]])
        y = np.concatenate([y, y[:1]])

    x0 = x[:-1]
    y0 = y[:-1]
    x1 = x[1:]
    y1 = y[1:]

    # Broadcast to (edges, points)
    py_e = py[None, :]
    px_e = px[None, :]

    # Edge crosses the scanline?
    cond = (y0[:, None] > py_e) != (y1[:, None] > py_e)
    # x coordinate of intersection of edge with scanline
    denom = (y1 - y0)[:, None]
    denom = np.where(np.abs(denom) < 1e-15, 1e-15, denom)

    xinters = (
        x0[:, None] + (px_e * 0 + 1) * (x1 - x0)[:, None] * (py_e - y0[:, None]) / denom
    )

    hit = cond & (px_e < xinters)
    inside = np.bitwise_xor.reduce(hit, axis=0)
    return inside


def _rasterise_even_odd(
    rings: List[np.ndarray], R: int, C: int, supersample: int
) -> np.ndarray:
    """Return (R,C) fractional coverage using even-odd fill over 'rings'."""
    s = max(1, int(supersample))
    # Sub-pixel centres in r,c space
    rr = np.arange(R, dtype=float)[:, None] + (np.arange(s, dtype=float) + 0.5) / s
    cc = np.arange(C, dtype=float)[None, :] + (np.arange(s, dtype=float) + 0.5) / s

    # Full grid
    rr_grid = np.repeat(rr[:, None, :], C, axis=1)  # (R,C,s)
    rr_grid = np.repeat(rr_grid[:, :, None, :], s, axis=2)  # (R,C,s,s)
    cc_grid = np.repeat(cc[None, :, :], R, axis=0)
    cc_grid = np.repeat(cc_grid[:, :, None, :], s, axis=2)

    # Flatten to points
    rr_f = rr_grid.reshape(-1)
    cc_f = cc_grid.reshape(-1)

    # Even-odd across all rings
    inside_any = np.zeros(rr_f.shape, dtype=bool)
    for ring in rings:
        inside_any ^= _points_in_ring_evenodd(cc_f, rr_f, ring)  # x=col, y=row

    # Aggregate back to (R,C)
    inside_any = inside_any.reshape(R, C, s, s)
    frac = inside_any.mean(axis=(2, 3)).astype(float)
    return frac


def voxelise_roi_to_mask(roi: ROI, geom: DoseGridGeom, cfg: DVHConfig) -> np.ndarray:
    """
    Voxelise an ROI (with rings/holes) onto the provided geometry.

    Returns a mask with shape (num_slices_with_contours, R, C) containing
    fractional occupancy in [0,1]. If multiple contours share a slice index,
    their rings are combined using even-odd parity.
    """
    R, C = geom.R, geom.C
    s = int(getattr(cfg, "inplane_supersample", 1) or 1)

    # Group contours by nearest k (slice), emit warning if multiple z across ROI
    z_vals = np.array([c.z_mm for c in roi.contours], dtype=float)
    if np.max(z_vals) - np.min(z_vals) > 1e-6:
        warnings.warn(
            f"ROI '{roi.name}' spans multiple z positions; assigning each contour to its nearest slice."
        )

    def _z_to_k(z_mm: float) -> int:
        # Interpret z_mm as offset along +w (mm) relative to ipp projected onto w
        # Map to fractional k then round to nearest index
        kf = geom._invert_gfo(float(z_mm))
        return int(np.clip(np.round(kf), 0, geom.K - 1))

    by_k: dict[int, List[np.ndarray]] = {}
    for contour in roi.contours:
        k = _z_to_k(contour.z_mm)
        # Each contour carries a list of rings (outer, inner, ...)
        for ring in contour.points_rc:
            by_k.setdefault(k, []).append(np.asarray(ring, dtype=float))

    if not by_k:
        return np.zeros((0, R, C), dtype=float)

    masks = []
    for k in sorted(by_k.keys()):
        rings = by_k[k]
        mask2d = _rasterise_even_odd(rings, R, C, s)
        masks.append(mask2d)

    return np.stack(masks, axis=0)
