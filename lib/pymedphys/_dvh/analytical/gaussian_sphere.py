from __future__ import annotations

import numpy as np

"""
Sphere + isotropic Gaussian dose analytical cumulative DVH.

From Walker & Byrne (2024):
D(r) = A * exp(-r^2 / (2 * sigma^2)) with 0 <= r <= R.
Invert to r(D) = sigma * sqrt(2 * ln(A / D)) (for D <= A). Cumulative V(D) = (4/3) pi * min(R, r(D))^3. :contentReference[oaicite:13]{index=13}
"""


def gaussian_sphere_v(D: np.ndarray, A: float, sigma: float, R: float) -> np.ndarray:
    """
    Normalised cumulative DVH for a sphere in an isotropic Gaussian.

    Parameters
    ----------
    D : array-like dose (Gy)
    A : peak dose at r=0 (Gy)
    sigma : Gaussian width (mm)
    R : sphere radius (mm)

    Returns
    -------
    V(D)/V_total in [0,1]
    """
    D = np.asarray(D, dtype=float)
    Vtot = (4.0 / 3.0) * np.pi * R**3
    with np.errstate(divide="ignore"):
        rD = sigma * np.sqrt(
            np.maximum(0.0, 2.0 * np.log(np.maximum(A / np.maximum(D, 1e-30), 1.0)))
        )
    rcap = np.minimum(R, rD)
    V = (4.0 / 3.0) * np.pi * rcap**3
    V = np.where(D > A, 0.0, V)
    return V / Vtot
