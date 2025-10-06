# -*- coding: utf-8 -*-
"""
Closed-form, orientation-aware analytical cumulative DVHs for the Nelms 2015 shapes.

Implements V(D) = fractional volume receiving at least dose D for:

- Cylinder:
  * axis ‖ gradient (IEC Y / “SI”): V(D) = 1 - β
  * axis ⟂ gradient (IEC Z / “AP”): V(D) = 1/2 - (1/π)[arcsin(u) + u*sqrt(1-u^2)]
    where u = 2β - 1

- Cone:
  * axis ‖ gradient (IEC Y / “SI”): V(D) = 1 - β^3
  * axis ⟂ gradient (IEC Z / “AP”): closed form from Nelms Appendix (rotated cone)

β = (D - Dmin) / (Dmax - Dmin)  clipped to [0, 1]

References:
- Nelms et al, Med Phys 42(8):4435–4448, 2015. (methods & closed forms)  :contentReference[oaicite:3]{index=3}
- Ebert et al, Phys Med Biol 55:N337–N346, 2010. (independent DVH calc context)  :contentReference[oaicite:4]{index=4}
- Walker & Byrne, Med Dosim (in press/2024). (small-volume DVH behaviour)  :contentReference[oaicite:5]{index=5}
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "nelms_cylinder_v",
    "nelms_cone_v",
    "nelms_rotated_cone_v",
]


def _beta(D: np.ndarray, dmin: float, dmax: float) -> np.ndarray:
    """Fractional position along the gradient, clipped to [0, 1]."""
    denom = float(dmax) - float(dmin)
    if denom <= 0:
        raise ValueError("Dmax must be > Dmin")
    b = (np.asarray(D, dtype=np.float64) - float(dmin)) / denom
    return np.clip(b, 0.0, 1.0)


def nelms_cylinder_v(
    D: np.ndarray, Dmin: float, Dmax: float, grad: str = "SI"
) -> np.ndarray:
    """
    Cumulative DVH V(D) for a cylinder.

    Parameters
    ----------
    D : array-like
        Dose array (Gy).
    Dmin, Dmax : float
        Min/max dose (Gy) within the structure along the gradient.
    grad : {"SI","AP"}
        "SI": cylinder axis ‖ gradient (IEC Y)  -> simple linear tail
        "AP": cylinder axis ⟂ gradient (IEC Z) -> circular segment integral form

    Returns
    -------
    V : np.ndarray
        Fractional volume receiving ≥ D (monotone decreasing from 1 to 0).
    """
    D = np.asarray(D, dtype=np.float64)
    b = _beta(D, Dmin, Dmax)

    if grad.upper() == "SI":
        # Axis || gradient: cross-section area constant; tail is linear in β
        V = 1.0 - b
    elif grad.upper() == "AP":
        # Axis ⟂ gradient: use circular segment integral
        # u in [-1,1], where u = 2β - 1
        u = 2.0 * b - 1.0
        # guard small numerical excursions
        u = np.clip(u, -1.0, 1.0)
        V = 0.5 - (np.arcsin(u) + u * np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))) / np.pi
    else:
        raise ValueError("grad must be 'SI' or 'AP'")

    # Impose cumulative behaviour outside [Dmin,Dmax]
    V = np.where(D <= Dmin, 1.0, V)
    V = np.where(D >= Dmax, 0.0, V)
    # Numerical monotonicity clean-up
    return np.maximum.accumulate(V[::-1])[::-1]


def nelms_cone_v(
    D: np.ndarray, Dmin: float, Dmax: float, grad: str = "SI"
) -> np.ndarray:
    """
    Cumulative DVH V(D) for a right circular cone.

    Parameters
    ----------
    D : array-like
        Dose array (Gy).
    Dmin, Dmax : float
        Min/max dose (Gy) within the structure along the gradient.
    grad : {"SI","AP"}
        "SI": cone axis ‖ gradient (IEC Y)  -> V(D) = 1 - β^3
        "AP": cone axis ⟂ gradient (IEC Z) -> rotated cone (use nelms_rotated_cone_v)

    Returns
    -------
    V : np.ndarray
        Fractional volume receiving ≥ D.
    """
    if grad.upper() == "SI":
        D = np.asarray(D, dtype=np.float64)
        b = _beta(D, Dmin, Dmax)
        V = 1.0 - b**3
        V = np.where(D <= Dmin, 1.0, V)
        V = np.where(D >= Dmax, 0.0, V)
        return np.maximum.accumulate(V[::-1])[::-1]
    elif grad.upper() == "AP":
        return nelms_rotated_cone_v(D, Dmin, Dmax)
    else:
        raise ValueError("grad must be 'SI' or 'AP'")


def nelms_rotated_cone_v(D: np.ndarray, Dmin: float, Dmax: float) -> np.ndarray:
    """
    Rotated cone (axis ⟂ gradient): cumulative DVH per Nelms (Appendix).

    Uses the closed form (their Eq. A7) expressed in dose terms with
    Δ = Dmax - Dmin, Σ = Dmax + Dmin and u = (2D - Σ)/Δ ∈ [-1,1]:

    V(D) = 1/2
           - (2D-Σ)/(πΔ) * sqrt( 1 - (2D-Σ)^2 / Δ^2 )
           - (1/π) * arcsin( (2D-Σ)/Δ )
           + (1/π) * ((2D-Σ)^3 / Δ^3) * arsech( |(2D-Σ)| / Δ )

    Notes
    -----
    The final 'arsech' term in the publication is one convenient closed-form
    parameterisation; numerically we guard domains and return 0/1 outside.
    See Nelms et al. 2015 Appendix for the derivation.  :contentReference[oaicite:6]{index=6}
    """
    D = np.asarray(D, dtype=np.float64)
    Δ = float(Dmax) - float(Dmin)
    if Δ <= 0:
        raise ValueError("Dmax must be > Dmin")
    Σ = float(Dmax) + float(Dmin)

    # Normalised coordinate u in [-1, 1]
    u = (2.0 * D - Σ) / Δ
    u = np.clip(u, -1.0, 1.0)

    # helper: area terms
    root = np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))
    base = 0.5 - (u * root) / np.pi - np.arcsin(u) / np.pi

    # arsech(x) = arcosh(1/x) for 0 < x <= 1 ; avoid 0/∞
    x = np.clip(np.abs(u), 1e-12, 1.0)
    arsech = np.arccosh(1.0 / x)
    cubic_term = (u**3) * arsech / np.pi

    V = base + cubic_term

    # Clamp outside range, enforce monotonicity
    V = np.where(D <= Dmin, 1.0, V)
    V = np.where(D >= Dmax, 0.0, V)
    return np.maximum.accumulate(V[::-1])[::-1]
