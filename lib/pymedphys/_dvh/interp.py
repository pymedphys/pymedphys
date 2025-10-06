# pymedphys/_dvh/interp.py
from __future__ import annotations

import numpy as np

# Use the fast, well-tested interpolator from PyMedPhys.
from pymedphys.interpolate import interp as _interp


def trilinear_sample(
    dose_krC: np.ndarray,
    points_krc: np.ndarray,
    *,
    bounds_error: bool = True,
    extrap_fill_value: float | None = None,
) -> np.ndarray:
    """
    Trilinear interpolation wrapper over pymedphys.interpolate.interp.

    Parameters
    ----------
    dose_krC : (K,R,C) ndarray
        Dose values (Gy) on an orthogonal index grid (0..K-1, 0..R-1, 0..C-1).
    points_krc : (N,3) ndarray
        Query points in *index* coordinates (k, r, c).
    bounds_error : bool
        Raise if any query point lies outside grid. If False, fill with `extrap_fill_value`.
    extrap_fill_value : float or None
        Value for out-of-bounds points when `bounds_error` is False. If None, np.nan is used.

    Returns
    -------
    values : (N,) ndarray
        Interpolated dose values (Gy) at query points.
    """
    dose = np.asarray(dose_krC, dtype=float)
    pts = np.asarray(points_krc, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points_krc must be of shape (N, 3)")

    K, R, C = dose.shape
    axes_known = [
        np.arange(K, dtype=float),
        np.arange(R, dtype=float),
        np.arange(C, dtype=float),
    ]

    vals = _interp(
        axes_known=axes_known,
        values=dose,
        points_interp=pts,
        bounds_error=bounds_error,
        extrap_fill_value=extrap_fill_value,
    )
    return vals
