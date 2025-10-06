# dvhlib/validation.py
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .analytics import nelms_linear_dvh, sphere_gaussian_dvh
from .dicom_io import load_rtdose, load_rtstruct
from .dvh import compute_dvh, dose_at_volume
from .voxelise import voxelise_roi


@dataclass
class NelmsCase:
    struct_path: str
    dose_path: str
    roi_name: str
    shape: str  # 'cone' or 'cylinder' (or 'sphere')
    gradient: str  # 'SI' or 'AP'
    expected_dmin: float
    expected_dmax: float


def _find_dicom_pair(root: str, pat: str) -> Tuple[str, str]:
    rts = sorted(glob.glob(os.path.join(root, "**", "*RTSTRUCT*.dcm"), recursive=True))
    rtd = sorted(glob.glob(os.path.join(root, "**", "*RTDOSE*.dcm"), recursive=True))
    if not rts or not rtd:
        raise FileNotFoundError("Could not find RTSTRUCT/RTDOSE under: " + root)
    # Naive: pick first matching pair (you will likely wire better logic in your integration)
    return rts[0], rtd[0]


def validate_nelms_linear_from_dicom(
    root: str,
    roi_selector: str,
    shape: str,
    gradient: str,
    dvh_bins: int = 200000,
    supersample=(1, 1, 1),
    method="sbi",
    endcap="half",
    abs_tol: float = 0.02,
) -> Dict[str, float]:
    """Load a Nelms test case from DICOM and compare computed DVH against closed-form analytic curve.

    Parameters
    ----------
    root : directory containing RTSTRUCT/RTDOSE for one test object
    roi_selector : ROI name (substring) to select the test structure (e.g. 'cone' or 'cylinder')
    shape, gradient : as per analytics.nelms_linear_dvh
    abs_tol : allowed absolute deviation in cumulative volume (fraction) across full dose range

    Returns
    -------
    dict with 'max_abs_diff' and a few Dxx comparisons.
    """
    rtstruct, rtdose = _find_dicom_pair(root, "*.dcm")
    dose = load_rtdose(rtdose)
    rois = load_rtstruct(rtstruct, roi_selector=roi_selector)
    if not rois:
        raise RuntimeError(f"No ROI matched '{roi_selector}' in {rtstruct}")
    roi = rois[0]

    frac, voxvol = voxelise_roi(
        dose, roi, supersample=supersample, method=method, endcap=endcap
    )
    dvh = compute_dvh(dose.dose_gy, frac, voxvol, bins=dvh_bins)
    Dedges = dvh["dose_bin_edges_gy"]
    dmid = 0.5 * (Dedges[:-1] + Dedges[1:])
    Vcalc = dvh["dvh_cum_frac"]

    Dmin = float(dmid[0])
    Dmax = float(dmid[-1])
    Vanal = nelms_linear_dvh(shape, gradient, dmid, Dmin, Dmax)
    max_abs = float(np.max(np.abs(Vcalc - Vanal)))
    if max_abs > abs_tol:
        raise AssertionError(
            f"Nelms DVH deviation {max_abs:.3f} exceeds tolerance {abs_tol:.3f}"
        )
    return {
        "max_abs_diff": max_abs,
        "D95_diff_pct": 100.0
        * (
            dose_at_volume(Dedges, dvh["dvh_cum_cc"], 0.95 * dvh["dvh_cum_cc"][0])
            - np.interp(0.95, Vanal[::-1], dmid[::-1])
        )
        / (Dmax - Dmin + 1e-6),
    }


def validate_sphere_gaussian_programmatic(
    R_mm: float = 10.0,
    sigma_mm: float = 10.0,
    A_gy: float = 10.0,
    grid_mm: float = 1.0,
    extent_mm: float = 60.0,
    dvh_bins: int = 200000,
    abs_tol: float = 5e-3,
) -> Dict[str, float]:
    """Generate an in-memory sphere + Gaussian dataset (no DICOM) and confirm DVH vs analytic curve.

    Returns dict with 'max_abs_diff'.
    """
    # Build grid
    ax = np.arange(-extent_mm / 2, extent_mm / 2 + grid_mm, grid_mm, dtype=float)
    X, Y, Z = np.meshgrid(ax, ax, ax, indexing="xy")
    r = np.sqrt(X**2 + Y**2 + Z**2)
    dose = A_gy * np.exp(-0.5 * (r / sigma_mm) ** 2)

    # Voxelise sphere analytically (partial volume by centre-in-sphere approximation for speed)
    mask = (r <= R_mm).astype(np.float32)
    voxvol = grid_mm**3

    from .dvh import compute_dvh

    dvh = compute_dvh(dose, mask, voxvol, bins=dvh_bins)
    Dedges = dvh["dose_bin_edges_gy"]
    dmid = 0.5 * (Dedges[:-1] + Dedges[1:])
    Vcalc = dvh["dvh_cum_frac"]

    Vanal = sphere_gaussian_dvh(dmid, A_gy, sigma_mm, R_mm)
    max_abs = float(np.max(np.abs(Vcalc - Vanal)))
    if max_abs > abs_tol:
        raise AssertionError(
            f"Sphere+Gaussian DVH deviation {max_abs:.4f} exceeds tolerance {abs_tol:.4f}"
        )
    return {"max_abs_diff": max_abs}
