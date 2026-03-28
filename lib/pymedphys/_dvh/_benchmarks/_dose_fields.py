"""Analytical dose field evaluation functions.

Evaluate dose at given coordinates for standard analytical dose
distributions used in the Tier 1 benchmark suite. These functions
are independent of structure geometry and can be used to generate
dose grids, validate interpolation, or build benchmark datasets.

See RFC §9 Task 1.2.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._benchmarks._geometry import _validate_positive


def linear_gradient_dose(
    z_mm: npt.ArrayLike,
    d0_gy: float,
    gradient_gy_per_mm: float,
) -> npt.NDArray[np.float64]:
    """Evaluate a linear dose gradient D(z) = D₀ + g·z.

    Parameters
    ----------
    z_mm : array_like
        Position(s) along the gradient axis in mm.
    d0_gy : float
        Dose at z = 0 in Gy.
    gradient_gy_per_mm : float
        Dose gradient in Gy/mm. May be positive, negative, or zero.

    Returns
    -------
    NDArray[np.float64]
        Dose in Gy at each position.
    """
    z = np.atleast_1d(np.asarray(z_mm, dtype=np.float64))
    return d0_gy + gradient_gy_per_mm * z


def radial_gaussian_dose(
    r_mm: npt.ArrayLike,
    amplitude_gy: float,
    sigma_mm: float,
) -> npt.NDArray[np.float64]:
    """Evaluate a radial Gaussian dose field D(r) = A·exp(-r²/(2σ²)).

    Parameters
    ----------
    r_mm : array_like
        Radial distance(s) from the field centre in mm.
    amplitude_gy : float
        Peak dose at r = 0 in Gy. Must be > 0.
    sigma_mm : float
        Standard deviation (width) of the Gaussian in mm. Must be > 0.

    Returns
    -------
    NDArray[np.float64]
        Dose in Gy at each radial distance.
    """
    _validate_positive(amplitude_gy=amplitude_gy, sigma_mm=sigma_mm)
    r = np.atleast_1d(np.asarray(r_mm, dtype=np.float64))
    return amplitude_gy * np.exp(-(r**2) / (2.0 * sigma_mm**2))
