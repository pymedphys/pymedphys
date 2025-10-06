# pymedphys/_dvh/validate/nelms_analytical.py
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Analytical DVH "best-practice" forms for the Nelms datasets
#
# These return *differential* DVH densities v(D) (i.e., pdfs) normalised so that
# ∫_{Dmin}^{Dmax} v(D) dD = 1 and ∫ D v(D) dD = D_mean. Closed forms follow
# directly from geometry with a 1D linear dose gradient, as described by
# Nelms et al., Med Phys 42(8):4435–4448, 2015. :contentReference[oaicite:1]{index=1}
# ---------------------------------------------------------------------------


def _inside(D: np.ndarray, Dmin: float, Dmax: float) -> np.ndarray:
    """Boolean mask for D within [Dmin, Dmax]."""
    return (D >= Dmin) & (D <= Dmax)


def nelms_cylinder_v(D: np.ndarray, Dmin: float, Dmax: float, grad: str) -> np.ndarray:
    """
    Differential DVH v(D) for a right circular cylinder under a linear 1D gradient.

    Parameters
    ----------
    D : array-like
        Dose values (Gy).
    Dmin, Dmax : float
        Minimum and maximum dose (Gy) across the structure.
    grad : {'SI','AP'}
        'SI' -> gradient along cylinder axis (uniform pdf).
        'AP' -> gradient across diameter (semi-circular pdf).

    Returns
    -------
    v : ndarray
        Differential DVH (pdf), normalised on [Dmin, Dmax].
    """
    D = np.asarray(D, dtype=float)
    v = np.zeros_like(D, dtype=float)
    Δ = float(Dmax - Dmin)
    Σ = float(Dmax + Dmin)
    m = _inside(D, Dmin, Dmax)

    g = grad.upper()
    if g == "SI":
        v[m] = 1.0 / Δ
    elif g == "AP":
        # Dimensionless position across the diameter
        t = (2.0 * D - Σ) / Δ
        t = np.clip(t, -1.0, 1.0)
        v[m] = (2.0 / (np.pi * Δ)) * np.sqrt(1.0 - t[m] ** 2)
    else:
        raise ValueError("grad must be 'SI' or 'AP'")

    return v


def nelms_cone_v(D: np.ndarray, Dmin: float, Dmax: float, grad: str) -> np.ndarray:
    """
    Differential DVH v(D) for a right circular cone with a linear 1D gradient.

    Parameters
    ----------
    D : array-like
        Dose values (Gy).
    Dmin, Dmax : float
        Minimum and maximum dose (Gy).
    grad : {'SI','AP'}
        'SI' -> gradient along cone axis (pdf ∝ (D-Dmin)^2).
        'AP' -> gradient across base diameter (dimensionless closed form; height cancels).

    Returns
    -------
    v : ndarray
        Differential DVH (pdf), normalised on [Dmin, Dmax].

    Notes
    -----
    - SI case: with y along the cone axis, A(y) ∝ y^2 and D = Dmin + (Δ/H) y
      ⇒ v(D) = 3 (D - Dmin)^2 / Δ^3.

    - AP case: analytical area of the x = const cross-section is
        A(x) = H [ √(R^2 - x^2) - (x^2/R) ln((R + √(R^2 - x^2)) / |x|) ]
      Using u = |x|/R = |(2D-Σ)/Δ|, height H cancels in v(D) and R drops out:
        v(D) = (6 / (π Δ)) [ √(1-u^2) - u^2 ln((1 + √(1-u^2)) / u) ].
      This matches the rotated-cone form in Nelms (Appendix), expressed without R,H. :contentReference[oaicite:2]{index=2}
    """
    D = np.asarray(D, dtype=float)
    v = np.zeros_like(D, dtype=float)
    Δ = float(Dmax - Dmin)
    Σ = float(Dmax + Dmin)
    m = _inside(D, Dmin, Dmax)

    g = grad.upper()
    if g == "SI":
        d = np.zeros_like(D)
        d[m] = D[m] - Dmin
        v[m] = 3.0 * d[m] ** 2 / (Δ**3)
    elif g == "AP":
        # Dimensionless distance from mid-dose
        u = np.abs((2.0 * D - Σ) / Δ)
        # Numerically robust evaluation at u=0 and u≈1
        u = np.clip(u, 0.0, 1.0)
        s = np.sqrt(1.0 - u**2)
        # Avoid log(0) but preserve the u^2 * log(...) -> 0 limit as u -> 0
        with np.errstate(divide="ignore", invalid="ignore"):
            logterm = np.log((1.0 + s) / np.maximum(u, 1e-300))
        core = s - u**2 * logterm
        v[m] = (6.0 / (np.pi * Δ)) * core[m]
        # Exact u=0 limit: v = 6/(π Δ)
        at_mid = (u == 0.0) & m
        v[at_mid] = 6.0 / (np.pi * Δ)
        # Exact u=1 limit is zero
        at_edge = (u == 1.0) & m
        v[at_edge] = 0.0
    else:
        raise ValueError("grad must be 'SI' or 'AP'")

    return v


# ---------------------------------------------------------------------------
# (Optional) cumulative tails V(D) = fraction with dose ≥ D on [Dmin, Dmax].
# These are handy when comparing against cumulative DVHs directly.
# ---------------------------------------------------------------------------


def nelms_cylinder_V(D: np.ndarray, Dmin: float, Dmax: float, grad: str) -> np.ndarray:
    """Cumulative (tail) DVH for cylinder: V(D) = ∫_D^{Dmax} v(s) ds."""
    D = np.asarray(D, dtype=float)
    V = np.zeros_like(D, dtype=float)
    Δ = float(Dmax - Dmin)
    Σ = float(Dmax + Dmin)
    g = grad.upper()

    if g == "SI":
        V = np.clip((Dmax - D) / Δ, 0.0, 1.0)
    elif g == "AP":
        t = np.clip((2.0 * D - Σ) / Δ, -1.0, 1.0)
        # Circular-segment area fraction
        V = (np.arccos(t) - t * np.sqrt(1.0 - t**2)) / np.pi
    else:
        raise ValueError("grad must be 'SI' or 'AP'")
    return V


def nelms_cone_V(D: np.ndarray, Dmin: float, Dmax: float, grad: str) -> np.ndarray:
    """Cumulative (tail) DVH for cone: V(D) = ∫_D^{Dmax} v(s) ds."""
    D = np.asarray(D, dtype=float)
    V = np.zeros_like(D, dtype=float)
    Δ = float(Dmax - Dmin)
    Σ = float(Dmax + Dmin)
    g = grad.upper()

    if g == "SI":
        # From v(D) = 3 (D-Dmin)^2 / Δ^3
        x = np.clip((D - Dmin) / Δ, 0.0, 1.0)
        V = 1.0 - x**3
    elif g == "AP":
        # Rotated cone – dimensionless closed form (Nelms Appendix A7)
        u = np.clip((2.0 * D - Σ) / Δ, -1.0, 1.0)
        s = np.sqrt(1.0 - u**2)
        # arsech(|u|) = arcosh(1/|u|) for 0<|u|≤1; define value 0 at u=0 by limit.
        with np.errstate(divide="ignore", invalid="ignore"):
            arsech = np.where(
                np.abs(u) > 0,
                np.arccosh(1.0 / np.abs(u)),
                0.0,
            )
        V = (
            0.5
            - (2.0 / np.pi) * u * s
            - (1.0 / np.pi) * np.arcsin(u)
            + (1.0 / np.pi) * (u**3) * arsech
        )
        # Clip numerically
        V = np.clip(V, 0.0, 1.0)
    else:
        raise ValueError("grad must be 'SI' or 'AP'")
    return V
