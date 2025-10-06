# -*- coding: utf-8 -*-
"""
Validation harness for DVH analytics.

Provides:
- validate_gaussian_sphere(cfg, R_mm=10.0, ...): float (percent RMS)
- validate_nelms_cone_cyl(cfg, shape, grad, ...): tuple[float, float]
    returns (percent RMS volume-difference, max dose-at-volume error in % of ΔD)

References:
- Ebert et al., Phys Med Biol 55:N337–N346 (2010) – independent DVH calc & comparison.
- Nelms et al., Med Phys 42(8):4435–4448 (2015) – closed-form DVHs for cylinder/cone.
"""

from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np

try:
    # Only for type hints; not required at runtime
    from pymedphys._dvh.config import DVHConfig  # noqa: F401
except Exception:  # pragma: no cover - hints only
    DVHConfig = object  # type: ignore[misc,assignment]

__all__ = ["validate_gaussian_sphere", "validate_nelms_cone_cyl"]


# ------------------------------ #
# Analytical DVH helper formulae #
# ------------------------------ #


def _beta(D: np.ndarray, dmin: float, dmax: float) -> np.ndarray:
    """Normalised position along the gradient, clipped to [0, 1]."""
    D = np.asarray(D, dtype=np.float64)
    denom = float(dmax) - float(dmin)
    if denom <= 0:
        raise ValueError("Dmax must be > Dmin")
    b = (D - float(dmin)) / denom
    return np.clip(b, 0.0, 1.0)


def nelms_cylinder_v(
    D: np.ndarray, Dmin: float, Dmax: float, grad: str = "SI"
) -> np.ndarray:
    """
    Cumulative DVH V(D) for a cylinder with a linear 1-D dose gradient.

    grad:
        "SI": cylinder axis ‖ gradient (IEC Y) -> V = 1 - β
        "AP": cylinder axis ⟂ gradient (IEC Z) -> circular-segment integral
              V = 1/2 - (arcsin(u) + u*sqrt(1-u^2))/π, with u = 2β - 1
    """
    D = np.asarray(D, dtype=np.float64)
    b = _beta(D, Dmin, Dmax)

    g = grad.upper()
    if g == "SI":
        V = 1.0 - b
    elif g == "AP":
        u = np.clip(2.0 * b - 1.0, -1.0, 1.0)
        V = 0.5 - (np.arcsin(u) + u * np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))) / np.pi
    else:
        raise ValueError("grad must be 'SI' or 'AP'")

    # Clamp outside range and enforce monotonicity
    V = np.where(D <= Dmin, 1.0, V)
    V = np.where(D >= Dmax, 0.0, V)
    return np.maximum.accumulate(V[::-1])[::-1]


def nelms_rotated_cone_v(D: np.ndarray, Dmin: float, Dmax: float) -> np.ndarray:
    """
    Rotated cone (axis ⟂ gradient): cumulative DVH per Nelms 2015 Appendix (Eq. A7).

    Uses Δ = Dmax - Dmin, Σ = Dmax + Dmin and u = (2D - Σ)/Δ ∈ [-1,1]:
      V(D) = 1/2 - (u*sqrt(1-u^2))/π - arcsin(u)/π + (u^3/π) * arsech(|u|)

    Numerically: arsech(x) = arcosh(1/x), with domain guard.
    """
    D = np.asarray(D, dtype=np.float64)
    Δ = float(Dmax) - float(Dmin)
    if Δ <= 0:
        raise ValueError("Dmax must be > Dmin")
    Σ = float(Dmax) + float(Dmin)

    u = np.clip((2.0 * D - Σ) / Δ, -1.0, 1.0)
    root = np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))
    base = 0.5 - (u * root) / np.pi - np.arcsin(u) / np.pi

    x = np.clip(np.abs(u), 1e-12, 1.0)
    arsech = np.arccosh(1.0 / x)
    V = base + (u**3) * arsech / np.pi

    V = np.where(D <= Dmin, 1.0, V)
    V = np.where(D >= Dmax, 0.0, V)
    return np.maximum.accumulate(V[::-1])[::-1]


def nelms_cone_v(
    D: np.ndarray, Dmin: float, Dmax: float, grad: str = "SI"
) -> np.ndarray:
    """Cumulative DVH V(D) for a right circular cone with a linear gradient."""
    g = grad.upper()
    if g == "SI":
        D = np.asarray(D, dtype=np.float64)
        b = _beta(D, Dmin, Dmax)
        V = 1.0 - b**3
        V = np.where(D <= Dmin, 1.0, V)
        V = np.where(D >= Dmax, 0.0, V)
        return np.maximum.accumulate(V[::-1])[::-1]
    if g == "AP":
        return nelms_rotated_cone_v(D, Dmin, Dmax)
    raise ValueError("grad must be 'SI' or 'AP'")


def gaussian_sphere_v(
    D: np.ndarray, A: float, R: float, sigma: float | None = None
) -> np.ndarray:
    """
    Analytical cumulative DVH for a sphere with a centred 3D Gaussian dose.

    Parameters
    ----------
    D : array-like
        Dose values (Gy) at which to evaluate the cumulative DVH V(D).
    A : float
        Peak dose at the sphere centre (Gy).
    R : float
        Sphere radius (mm).
    sigma : float
        Gaussian σ (mm). Defaults to R (convenient stress test).

    Returns
    -------
    V : np.ndarray
        Fractional volume receiving ≥ D (clipped to [0, 1], monotone decreasing).
    """
    if sigma is None:
        sigma = R

    D = np.asarray(D, dtype=np.float64)
    Dmax = float(A)
    Dedge = float(A) * np.exp(-(R**2) / (2.0 * sigma**2))

    # Core term for A*exp(-r^2/2σ^2), inverted to r(D)
    with np.errstate(divide="ignore", invalid="ignore"):
        ln_term = np.log(np.where(D > 0, Dmax / D, np.inf))
    core = (sigma / R) ** 3 * (2.0 * ln_term) ** 1.5

    V = np.where(D >= Dmax, 0.0, np.where(D <= Dedge, 1.0, core))
    V = np.clip(V, 0.0, 1.0)
    return np.maximum.accumulate(V[::-1])[::-1]


# ------------------------- #
# Numerical sampling engine #
# ------------------------- #


def _regular_lattice(
    x_min: float,
    x_max: float,
    dx: float,
    y_min: float,
    y_max: float,
    dy: float,
    z_min: float,
    z_max: float,
    dz: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create a regular lattice meshgrid (XY indexing)."""
    x = np.arange(x_min, x_max + 1e-9, dx, dtype=np.float64)
    y = np.arange(y_min, y_max + 1e-9, dy, dtype=np.float64)
    z = np.arange(z_min, z_max + 1e-9, dz, dtype=np.float64)
    X, Y, Z = np.meshgrid(x, y, z, indexing="xy")
    return X, Y, Z


def _cdf_numeric_from_samples(
    d_inside: np.ndarray, dvh_bins: int, dmin: float, dmax: float
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build a cumulative DVH V(D) from dose samples within the ROI.

    Returns dose bin centres and V(D) as fraction of samples with dose ≥ D.
    """
    # Define bins across the expected in-ROI dynamic range
    D_bins = np.linspace(float(dmin), float(dmax), int(dvh_bins), endpoint=True)
    d_sorted = np.sort(d_inside)
    N = d_sorted.size
    idx = np.searchsorted(d_sorted, D_bins, side="left")
    V = (N - idx).astype(np.float64) / float(N)
    V = np.maximum.accumulate(V[::-1])[::-1]
    V = np.clip(V, 0.0, 1.0)
    return D_bins, V


def _invert_v_to_d(
    doses: np.ndarray, vols: np.ndarray, v_targets: Iterable[float]
) -> np.ndarray:
    """Given cumulative DVH V(D), return D at requested volume fractions (linear interpolation)."""
    doses = np.asarray(doses, dtype=np.float64)
    vols = np.asarray(vols, dtype=np.float64)

    # Ensure monotone decreasing
    V = np.maximum.accumulate(vols[::-1])[::-1]
    # Invert by interpolating D(V) on the strictly decreasing segment
    # Build D as a function of V using unique V values
    V_unique, idx = np.unique(
        V[::-1], return_index=True
    )  # increasing in this reversed view
    D_unique = doses[::-1][idx]
    # Interpolate D at requested V (clip to ends)
    v_req = np.clip(np.asarray(list(v_targets), dtype=np.float64), 0.0, 1.0)
    return np.interp(v_req, V_unique, D_unique)


# ---------------------------- #
# Public validation entrypoints#
# ---------------------------- #


def validate_gaussian_sphere(
    cfg: "DVHConfig",
    R_mm: float = 10.0,
    sigma_mm: float | None = None,
    vox_mm: float = 1.0,
    A: float = 1.0,
    return_curves: bool = False,
) -> float | Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compare numerical vs analytical DVH for a sphere with Gaussian dose.

    Returns
    -------
    rms_percent : float
        Percent RMS of (V_num - V_ana) across the sampled dose axis.
    Optionally also returns (dose_bins, V_num, V_ana).
    """
    if sigma_mm is None:
        sigma_mm = R_mm

    # Sampling lattice sized just to cover the sphere (margin = half voxel)
    half = R_mm + vox_mm / 2.0
    sx = vox_mm / max(1, int(getattr(cfg, "inplane_supersample", 1)))
    sy = sx
    sz = vox_mm / max(1, int(getattr(cfg, "axial_supersample", 1)))

    X, Y, Z = _regular_lattice(-half, half, sx, -half, half, sy, -half, half, sz)
    r2 = X * X + Y * Y + Z * Z
    inside = r2 <= (R_mm**2 + 1e-9)

    doses = float(A) * np.exp(-r2 / (2.0 * sigma_mm**2))
    d_inside = doses[inside]

    if d_inside.size == 0:
        raise ValueError("No sample points inside sphere; check parameters.")

    # Dose range within ROI
    dmin = float(A) * np.exp(-(R_mm**2) / (2.0 * sigma_mm**2))
    dmax = float(A)

    D_bins, V_num = _cdf_numeric_from_samples(
        d_inside, int(getattr(cfg, "dvh_bins", 2000)), dmin, dmax
    )
    V_ana = gaussian_sphere_v(D_bins, A=float(A), R=float(R_mm), sigma=float(sigma_mm))

    diff = V_num - V_ana
    rms = float(np.sqrt(np.mean(diff * diff)) * 100.0)

    if return_curves:
        return rms, D_bins, V_num, V_ana
    return rms


def _analytic_cone_ap(d_bins: np.ndarray, dmin: float, dmax: float) -> np.ndarray:
    """
    Axial cone, linear 1D dose gradient along cone axis (AP).
    Cumulative DVH fraction v(D) = 1 - ((D-Dmin)/(Dmax-Dmin))**3 on [Dmin, Dmax].
    """
    d = np.asarray(d_bins, dtype=float)
    lo = min(dmin, dmax)
    hi = max(dmin, dmax)
    width = hi - lo if hi > lo else 1.0

    t = np.clip((d - lo) / width, 0.0, 1.0)
    v = 1.0 - t**3
    return v


def validate_nelms_cone_cyl(
    cfg: "DVHConfig",
    shape: str,
    grad: str,
    R_mm: float = 12.0,
    H_mm: float = 24.0,
    Dmin: float = 4.0,
    Dmax: float = 28.0,
    vox_mm: float = 1.0,
    v_check: Iterable[float] = (0.99, 0.95, 0.90, 0.50, 0.10, 0.05, 0.01),
) -> Tuple[float, float]:
    """
    Validate cylinder/cone DVH against Nelms closed-form references.

    Parameters
    ----------
    shape : {"cylinder","cone"}
    grad  : {"SI","AP"}  SI=Y-gradient (IEC1217), AP=Z-gradient

    Returns
    -------
    rms_percent : float
        Percent RMS of volume-difference across the sampled dose axis.
    dx_percent : float
        Max |D_num - D_ana| across v_check, expressed as % of ΔD = Dmax-Dmin.
    """
    g = grad.upper()
    s = shape.lower()

    # Lattice bounding box for the ROI
    half_R = R_mm + vox_mm / 2.0
    half_H = H_mm / 2.0 + vox_mm / 2.0
    sx = vox_mm / max(1, int(getattr(cfg, "inplane_supersample", 1)))
    sy = sx
    sz = vox_mm / max(1, int(getattr(cfg, "axial_supersample", 1)))

    # Axis is along Y for both shapes; gradient along Y ("SI") or Z ("AP")
    X, Y, Z = _regular_lattice(
        -half_R, half_R, sx, -half_H, half_H, sy, -half_R, half_R, sz
    )

    # ROI mask
    if s == "cylinder":
        inside = (X * X + Z * Z) <= (R_mm**2 + 1e-9)
        inside &= np.abs(Y) <= (H_mm / 2.0 + 1e-9)
    elif s == "cone":
        if g == "AP":
            v_analytic = _analytic_cone_ap(d_bins, dmin, dmax)  # noqa
        else:
            # Apex at y = -H/2, base radius R at y = +H/2
            y0 = (Y + H_mm / 2.0) / H_mm  # 0 -> apex, 1 -> base
            r_y = R_mm * np.clip(y0, 0.0, 1.0)
            inside = (X * X + Z * Z) <= (r_y**2 + 1e-9)
            inside &= (Y >= -H_mm / 2.0 - 1e-9) & (Y <= H_mm / 2.0 + 1e-9)
    else:
        raise ValueError("shape must be 'cylinder' or 'cone'")

    # Linear gradient dose
    if g == "SI":
        # Map Y in [-H/2, H/2] -> [Dmin, Dmax]
        beta = (Y + H_mm / 2.0) / H_mm
    elif g == "AP":
        # Map Z in [-R, R] -> [Dmin, Dmax]
        beta = (Z + R_mm) / (2.0 * R_mm)
    else:
        raise ValueError("grad must be 'SI' or 'AP'")

    doses = float(Dmin) + (float(Dmax) - float(Dmin)) * beta
    d_inside = doses[inside]

    # Numerical cumulative DVH
    D_bins, V_num = _cdf_numeric_from_samples(
        d_inside, int(getattr(cfg, "dvh_bins", 2000)), float(Dmin), float(Dmax)
    )

    # Analytical cumulative DVH
    if s == "cylinder":
        V_ana = nelms_cylinder_v(D_bins, float(Dmin), float(Dmax), grad=g)
    else:
        V_ana = nelms_cone_v(D_bins, float(Dmin), float(Dmax), grad=g)

    # Percent RMS of volume-difference
    diff = V_num - V_ana
    rms_percent = float(np.sqrt(np.mean(diff * diff)) * 100.0)

    # Dose-at-volume checks across selected V targets
    d_num = _invert_v_to_d(D_bins, V_num, v_check)
    d_ana = _invert_v_to_d(D_bins, V_ana, v_check)
    dx_percent = float(
        np.max(np.abs(d_num - d_ana)) / (float(Dmax) - float(Dmin)) * 100.0
    )

    return rms_percent, dx_percent
