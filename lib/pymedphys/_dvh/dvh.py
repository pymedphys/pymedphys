# pymedphys/_dvh/dvh.py
from __future__ import annotations

import numpy as np

from .config import DVHConfig
from .interp import trilinear_sample


def _subvoxel_offsets(S: int) -> np.ndarray:
    """Symmetric offsets within a voxel for S samples per axis.

    Returns values in (-0.5, 0.5) centred on 0, e.g.
    S=1 -> [0.0]; S=2 -> [-0.25, 0.25]; S=4 -> [-0.375, -0.125, 0.125, 0.375]
    """
    if S <= 1:
        return np.array([0.0], dtype=np.float64)
    # centres of S equal sub-intervals over [-0.5, 0.5]
    return (np.linspace(1, 2 * S - 1, S, dtype=np.float64) / (2.0 * S)) - 0.5


def compute_dvh(
    dose_krC: np.ndarray,
    mask_frac_krC: np.ndarray,
    voxel_size_mm: tuple[float, float, float] | None,
    cfg: DVHConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute cumulative DVH from a dose grid and a (fractional) mask.

    Parameters
    ----------
    dose_krC : (K,R,C) ndarray
        Dose array (Gy).
    mask_frac_krC : (K,R,C) ndarray
        Fractional mask (0..1).
    voxel_size_mm : tuple or None
        Present for API parity; sampling is done in index-space so it is unused here.
    cfg : DVHConfig
        Configuration (sampling factors, bins, dose_range etc).

    Returns
    -------
    dose_axis : (B,) ndarray
        Bin centres in Gy.
    cum : (B,) ndarray
        Cumulative V(≥D) (fractional volume), monotone ↓ from 1 to 0.
    """
    dose = np.asarray(dose_krC, dtype=np.float64)
    wmask = np.asarray(mask_frac_krC, dtype=np.float64)
    if dose.shape != wmask.shape:
        raise ValueError("dose and mask shapes must match")

    K, R, C = dose.shape

    # Build sub-voxel sampling pattern (index-space)
    Sa = max(1, int(cfg.axial_supersample))
    Sp = max(1, int(cfg.inplane_supersample))
    oa = _subvoxel_offsets(Sa)  # along k
    op = _subvoxel_offsets(Sp)  # along r and c

    # Target voxels (mask > 0)
    idx_k, idx_r, idx_c = np.nonzero(wmask > 0.0)
    if idx_k.size == 0:
        # No volume -> empty DVH over trivial axis
        dmin, dmax = float(np.nanmin(dose)), float(np.nanmax(dose))
        bin_edges = np.linspace(dmin, dmax, cfg.dvh_bins + 1, dtype=np.float64)
        centres = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        return centres, np.zeros_like(centres)

    pts_list = []
    wts_list = []

    # Generate sub-voxel sample points and weights per included voxel
    if cfg.subvoxel_dose_sample:
        # Vectorised construction for speed: build a block per (k,r,c)
        for k, r, c in zip(idx_k, idx_r, idx_c):
            # Anchor sub-sample lattice at the voxel CENTRE (k+0.5, r+0.5, c+0.5)
            kk = (k + 0.5) + oa[:, None, None]
            rr = (r + 0.5) + op[None, :, None]
            cc = (c + 0.5) + op[None, None, :]
            # meshgrid in index space (k, r, c)
            grid = np.stack(np.meshgrid(kk, rr, cc, indexing="ij"), axis=-1).reshape(
                -1, 3
            )
            pts_list.append(grid)
            # Weight: mask fraction equally split across sub-samples
            w_each = wmask[k, r, c] / float(Sa * Sp * Sp)
            wts_list.append(np.full((grid.shape[0],), w_each, dtype=np.float64))
        else:
            pts_list.append(np.array([[k + 0.5, r + 0.5, c + 0.5]], dtype=np.float64))
            wts_list.append(np.array([wmask[k, r, c]], dtype=np.float64))

    pts = np.concatenate(pts_list, axis=0)
    wts = np.concatenate(wts_list, axis=0)

    # Sample dose
    dvals = trilinear_sample(dose, pts, bounds_error=False, extrap_fill_value=0.0)

    # Histogram with weights
    dmin = float(np.nanmin(dvals))
    dmax = float(np.nanmax(dvals))
    if cfg.dose_range is not None:
        lo, hi = cfg.dose_range
        dmin = max(dmin, float(lo))
        dmax = min(dmax, float(hi))
    counts, edges = np.histogram(
        dvals, bins=int(cfg.dvh_bins), range=(dmin, dmax), weights=wts
    )
    tot_w = np.sum(wts)
    cum = np.cumsum(counts[::-1])[::-1] / (tot_w if tot_w > 0 else 1.0)
    # Enforce non-increasing cumulative DVH (robust to tiny round-off at steep gradients)
    if cum.size:
        cum = np.minimum.accumulate(cum)

    # Return bin centres and cumulative fraction
    centres = 0.5 * (edges[:-1] + edges[1:])
    return centres.astype(np.float64), cum.astype(np.float64)
