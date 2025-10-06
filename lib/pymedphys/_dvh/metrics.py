from __future__ import annotations

import numpy as np


def precision_band(d: np.ndarray, v: np.ndarray, n_eff: int):
    """
    ECDF-style precision band around a cumulative DVH v(d).

    For an empirical cumulative distribution from n samples, the vertical step is 1/n.
    A conservative precision band is therefore +/- 0.5/n at each dose bin (clipped to [0,1]).

    Parameters
    ----------
    d : (N,) array-like
        Dose bins (monotonic increasing).
    v : (N,) array-like
        Cumulative volume fractions in [0,1], monotonic decreasing or non-increasing.
    n_eff : int
        Effective independent samples.

    Returns
    -------
    lo, hi : (N,) arrays
        Lower and upper bounds (clipped to [0,1]) with total vertical width 1/n_eff.
    """
    d = np.asarray(d, dtype=float)
    v = np.asarray(v, dtype=float)
    if n_eff <= 0:
        raise ValueError("n_eff must be positive")

    half_step = 0.5 / float(n_eff)
    lo = np.clip(v - half_step, 0.0, 1.0)
    hi = np.clip(v + half_step, 0.0, 1.0)

    # Ensure band encloses v after clipping (numerical safety)
    lo = np.minimum(lo, v)
    hi = np.maximum(hi, v)

    return lo, hi
