from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..config import DVHConfig
from ..dicom_io import ROI, DoseGridGeom
from .polygon import rasterise_fraction


def _stack_polys_for_numba(polys: List[np.ndarray]) -> np.ndarray:
    """
    Pack a list of (Ni,2) polygons into a 3D array (P, Mmax, 2), pad with NaN row to mark end.
    """
    if len(polys) == 0:
        return np.full((1, 1, 2), np.nan, dtype=np.float32)
    mmax = max(p.shape[0] for p in polys)
    out = np.full(
        (len(polys) + 1, mmax, 2), np.nan, dtype=np.float32
    )  # +1 NaN sentinel
    for p, poly in enumerate(polys):
        out[p, : poly.shape[0], :] = poly.astype(np.float32)
    return out


def voxelise_roi_to_mask(roi: ROI, geom: DoseGridGeom, cfg: DVHConfig) -> np.ndarray:
    """
    Compute a fractional-occupancy mask aligned to the DOSE grid: (K,R,C) in [0,1].

    Strategy (right_prism):
      - Compute slab bounds along 'w' between adjacent contour planes; extend end-caps by half-slice if enabled.
      - For each K-slice whose w-distance lies within a slab, rasterise the 2D contours onto (R,C) with sub-sampling.

    Notes
    -----
    This follows the common “right-prism” approach used by several systems and analysed in Pepin et al. 2022. :contentReference[oaicite:9]{index=9}
    A linear SDF-like interpolation mode ('sdf_linear') is provided as an approximation to shape-based interpolation.
    """
    K, R, C = geom.shape
    # Prepare slab edges from ROI contour z_mm values
    z = np.array([c.z_mm for c in roi.contours], dtype=float)
    if z.size == 0:
        return np.zeros((K, R, C), dtype=np.float32)

    # Compute midpoints for slabs
    mids = None
    if z.size > 1:
        mids = (z[:-1] + z[1:]) * 0.5
    # For each contour, get lower/upper bounds
    lower = np.empty_like(z)
    upper = np.empty_like(z)
    for i in range(len(z)):
        lower[i] = z[i] if i == 0 else mids[i - 1]
        upper[i] = z[i] if i == len(z) - 1 else mids[i]
    if cfg.endcap_mode == "half_slice" and z.size > 1:
        # Extend end-caps by half the local spacing
        lower[0] = z[0] - (z[1] - z[0]) * 0.5
        upper[-1] = z[-1] + (z[-1] - z[-2]) * 0.5

    # Map each frame's w-distance (from ipp) for slice centres
    if K > 1:
        _ = geom.gfo[1] - geom.gfo[0]
        wdist_k = geom.gfo  # centre at given offset
    else:
        wdist_k = np.array([geom.gfo[0]])

    mask = np.zeros((K, R, C), dtype=np.float32)

    # Rasterise per K: find which contour slab covers this K, rasterise all polygons at that slab
    for slab_idx, c2d in enumerate(roi.contours):
        polys = [_ensure_closed(poly) for poly in c2d.points_rc]
        packed = _stack_polys_for_numba(polys)
        # find k indices within [lower, upper]
        k_sel = np.where((wdist_k >= lower[slab_idx]) & (wdist_k < upper[slab_idx]))[0]
        if k_sel.size == 0:
            continue
        # Rasterise once; reuse for all k in the slab (right_prism)
        frac = rasterise_fraction(R, C, packed, max(1, cfg.inplane_supersample))
        for k in k_sel:
            mask[k, :, :] = np.maximum(mask[k, :, :], frac)

    if cfg.voxelise_mode == "sdf_linear" and len(roi.contours) > 1:
        # Optional refinement: linear blend of adjacent slice fractions across k within [lower, upper]
        # (SDF-like behaviour; cheap approximation)
        for i in range(len(roi.contours) - 1):
            z0, z1 = z[i], z[i + 1]
            k_sel = np.where((wdist_k >= z0) & (wdist_k < z1))[0]
            if k_sel.size == 0:
                continue
            polys0 = _stack_polys_for_numba(
                [_ensure_closed(p) for p in roi.contours[i].points_rc]
            )
            polys1 = _stack_polys_for_numba(
                [_ensure_closed(p) for p in roi.contours[i + 1].points_rc]
            )
            frac0 = rasterise_fraction(R, C, polys0, max(1, cfg.inplane_supersample))
            frac1 = rasterise_fraction(R, C, polys1, max(1, cfg.inplane_supersample))
            for k in k_sel:
                t = (wdist_k[k] - z0) / (z1 - z0 + 1e-12)
                mask[k] = np.maximum(mask[k], (1 - t) * frac0 + t * frac1)

    return np.clip(mask, 0.0, 1.0).astype(np.float32)


def _ensure_closed(poly: np.ndarray) -> np.ndarray:
    """Ensure first point repeats at end for polygon closure during rasterisation."""
    if poly.shape[0] < 3:
        return poly
    if not np.allclose(poly[0], poly[-1]):
        return np.vstack([poly, poly[0]])
    return poly
