# dvhlib/analytics.py
from __future__ import annotations

from typing import Literal

import numpy as np

# ===== Nelms-style linear-gradient closed-form DVHs =====
# Using normalised dose variable:
#   xi = [2D - (Dmax + Dmin)] / (Dmax - Dmin), clamped to [-1,1]
# Pepin et al. provide the explicit expressions for cone & cylinder (SI/AP). :contentReference[oaicite:7]{index=7}
# We also include sphere (linear gradient) by direct integration of A(x)=pi(R^2-x^2).


def _xi(D, Dmin, Dmax):
    xi = (2.0 * D - (Dmax + Dmin)) / (Dmax - Dmin + 1e-12)
    return np.clip(xi, -1.0, 1.0)


def nelms_linear_dvh(
    shape: Literal["cylinder", "cone", "sphere"],
    gradient: Literal["SI", "AP"],
    D: np.ndarray,
    Dmin: float,
    Dmax: float,
) -> np.ndarray:
    """Normalised cumulative volume V(D) for Nelms test shapes with 1D linear dose gradient.

    Shapes:
      - 'cylinder': SI (axis-aligned), AP (perpendicular) — Pepin Eqs (3) & (5)
      - 'cone'    : SI, AP — Pepin Eqs (2) & (4)
      - 'sphere'  : linear gradient (derivation by direct area integration)

    Returns V in [0,1].
    """
    xi = _xi(D, Dmin, Dmax)
    if shape == "cylinder" and gradient == "SI":
        # V_SI^Cylinder(D) = 0.5*(1 - xi)
        V = 0.5 * (1.0 - xi)
    elif shape == "cylinder" and gradient == "AP":
        # V_AP^Cylinder(D) = 0.5 - (xi/pi)*sqrt(1-xi^2) - (1/pi)*arcsin(xi)
        V = (
            0.5
            - (xi / np.pi) * np.sqrt(np.maximum(0.0, 1.0 - xi**2))
            - (1.0 / np.pi) * np.arcsin(xi)
        )
    elif shape == "cone" and gradient == "SI":
        # V_SI^Cone(D) = 1 - (1/8)*(xi + 1)^3
        V = 1.0 - 0.125 * (xi + 1.0) ** 3
    elif shape == "cone" and gradient == "AP":
        # V_AP^Cone(D) = 1/2 - (2 xi / pi) sqrt(1-xi^2) - (1/pi) arcsin(xi) + (xi^3/pi) arcsech(|xi|)
        # arcsech(x) = arcosh(1/x); handle |xi| in (0,1]
        xi_abs = np.clip(np.abs(xi), 1e-12, 1.0)
        arcsech = np.arccosh(1.0 / xi_abs)
        V = (
            0.5
            - (2.0 * xi / np.pi) * np.sqrt(np.maximum(0.0, 1.0 - xi**2))
            - (1.0 / np.pi) * np.arcsin(xi)
            + (xi**3 / np.pi) * arcsech
        )
    elif shape == "sphere":
        # Linear gradient along one axis; sphere radius R; cumulative V(D) = (2 - 3 xi + xi^3)/4
        V = 0.25 * (2.0 - 3.0 * xi + xi**3)
    else:
        raise ValueError("Unsupported shape/gradient")
    # clamp outside
    V = np.where(D <= Dmin, 1.0, V)
    V = np.where(D >= Dmax, 0.0, V)
    return V


# ===== Sphere + 3D Gaussian dose (Walker & Byrne) =====
# D(r) = A * exp(-r^2 / (2 sigma^2)), r(D) = sigma * sqrt(2 ln(A/D)), and
# V(D) = (4/3) pi * min(R, r(D))^3  /  ((4/3) pi R^3)  for cumulative coverage.
# See Walker & Byrne, Methods §Synthetic structures and dose (Eqs (1)–(3)). :contentReference[oaicite:8]{index=8}


def sphere_gaussian_dvh(D: np.ndarray, A: float, sigma: float, R: float) -> np.ndarray:
    """Normalised cumulative DVH for a sphere of radius R with an isotropic 3D Gaussian dose centred at the sphere.

    Parameters
    ----------
    D : dose values (Gy), can be scalar or array
    A : maximum dose at centre (Gy)
    sigma : Gaussian width (mm)
    R : sphere radius (mm)

    Returns
    -------
    V : normalised cumulative volume in [0,1]
    """
    D = np.asarray(D, dtype=float)
    # where D>A, set 0; where D<=0 set 1
    V = np.ones_like(D)
    valid = (D > 0) & (D <= A)
    r = sigma * np.sqrt(2.0 * np.log(A / D[valid]))
    r = np.minimum(r, R)
    V[valid] = (r**3) / (R**3)
    V[D > A] = 0.0
    return V


def sphere_linear_dvh(D: np.ndarray, Dmin: float, Dmax: float) -> np.ndarray:
    """Convenience wrapper for shape='sphere' linear gradient."""
    return nelms_linear_dvh("sphere", "SI", D, Dmin, Dmax)
