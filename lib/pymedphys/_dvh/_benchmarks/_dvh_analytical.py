"""Closed-form cumulative DVH formulas for analytical benchmarks.

Each function computes V(D) — the volume (in mm³) receiving dose >= D —
for a specific combination of geometric shape and dose distribution.

These provide analytical ground truth for the Tier 1 benchmark suite.
Nelms et al. [14] showed that whole-curve validation against analytical
truth exposes failure modes that endpoint-only checks miss.

See RFC §9 Task 1.2, §8.1.1, and §8.1.2.

References
----------
.. [14] Nelms et al., "Variation in external beam treatment plan quality"
.. [17] Stanley et al., small-volume SRS benchmarks
.. [21] Walker and Byrne, analytical PCI/GI benchmarks
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pymedphys._dvh._benchmarks._geometry import (
    _validate_positive,
    cone_volume,
    cylinder_volume,
    sphere_volume,
)


def sphere_linear_gradient_dvh(
    dose_gy: npt.ArrayLike,
    radius_mm: float,
    d0_gy: float,
    gradient_gy_per_mm: float,
) -> npt.NDArray[np.float64]:
    """Cumulative DVH for a sphere in a linear dose gradient.

    Sphere centred at z=0. Dose field D(z) = d0 + g*z.

    Parameters
    ----------
    dose_gy : array_like
        Dose threshold(s) in Gy at which to evaluate V(D).
    radius_mm : float
        Sphere radius in mm. Must be > 0.
    d0_gy : float
        Dose at sphere centre (z=0) in Gy.
    gradient_gy_per_mm : float
        Dose gradient in Gy/mm. May be positive, negative, or zero.

    Returns
    -------
    NDArray[np.float64]
        Cumulative volume V(D) in mm³ at each dose threshold.
        V(D) = volume of sphere receiving dose >= D.
    """
    _validate_positive(radius_mm=radius_mm)
    dose = np.atleast_1d(np.asarray(dose_gy, dtype=np.float64))
    v_total = sphere_volume(radius_mm)
    r = radius_mm

    if gradient_gy_per_mm == 0.0:
        return np.where(dose <= d0_gy, v_total, 0.0)

    # Dmax = d0 + |g|*r (maximum dose in sphere, regardless of gradient sign)
    abs_g = abs(gradient_gy_per_mm)
    d_max = d0_gy + abs_g * r

    # h_cap = height of spherical cap receiving dose >= D
    # Unified formula for both positive and negative gradient
    h_cap = np.clip((d_max - dose) / abs_g, 0.0, 2.0 * r)

    # Spherical cap volume: V = (pi*h^2/3)(3r - h) where h is cap height
    # Note: RFC §9 Task 1.2 formula uses z₀ notation but labels it h;
    # the standard cap formula in terms of cap height h is (π/3)(3rh² - h³).
    result = (np.pi / 3.0) * (3.0 * r * h_cap**2 - h_cap**3)
    return np.clip(result, 0.0, v_total)


def cylinder_linear_gradient_dvh(
    dose_gy: npt.ArrayLike,
    radius_mm: float,
    height_mm: float,
    d0_gy: float,
    gradient_gy_per_mm: float,
) -> npt.NDArray[np.float64]:
    """Cumulative DVH for a cylinder in a linear dose gradient.

    Cylinder with base at z=0 and top at z=H. Dose field D(z) = d0 + g*z.

    Parameters
    ----------
    dose_gy : array_like
        Dose threshold(s) in Gy.
    radius_mm : float
        Cylinder radius in mm. Must be > 0.
    height_mm : float
        Cylinder height in mm. Must be > 0.
    d0_gy : float
        Dose at z=0 in Gy.
    gradient_gy_per_mm : float
        Dose gradient in Gy/mm.

    Returns
    -------
    NDArray[np.float64]
        Cumulative volume V(D) in mm³.
    """
    _validate_positive(radius_mm=radius_mm, height_mm=height_mm)
    dose = np.atleast_1d(np.asarray(dose_gy, dtype=np.float64))
    v_total = cylinder_volume(radius_mm, height_mm)

    if gradient_gy_per_mm == 0.0:
        return np.where(dose <= d0_gy, v_total, 0.0)

    abs_g = abs(gradient_gy_per_mm)
    d_max = max(d0_gy, d0_gy + gradient_gy_per_mm * height_mm)

    # Length of cylinder axis where dose >= D
    length = np.clip((d_max - dose) / abs_g, 0.0, height_mm)
    area = np.pi * radius_mm**2
    return np.clip(area * length, 0.0, v_total)


def cone_linear_gradient_dvh(
    dose_gy: npt.ArrayLike,
    base_radius_mm: float,
    height_mm: float,
    d0_gy: float,
    gradient_gy_per_mm: float,
) -> npt.NDArray[np.float64]:
    """Cumulative DVH for a cone in a linear dose gradient.

    Cone with apex at z=0 and base (radius R) at z=H.
    Dose field D(z) = d0 + g*z.

    For g > 0 (apex at low-dose end):
        V(D) = V_total * (1 - (z_D/H)^3)
    For g < 0 (apex at high-dose end):
        V(D) = V_total * (z_D/H)^3

    Parameters
    ----------
    dose_gy : array_like
        Dose threshold(s) in Gy.
    base_radius_mm : float
        Cone base radius in mm. Must be > 0.
    height_mm : float
        Cone height in mm. Must be > 0.
    d0_gy : float
        Dose at apex (z=0) in Gy.
    gradient_gy_per_mm : float
        Dose gradient in Gy/mm.

    Returns
    -------
    NDArray[np.float64]
        Cumulative volume V(D) in mm³.
    """
    _validate_positive(base_radius_mm=base_radius_mm, height_mm=height_mm)
    dose = np.atleast_1d(np.asarray(dose_gy, dtype=np.float64))
    v_total = cone_volume(base_radius_mm, height_mm)

    if gradient_gy_per_mm == 0.0:
        return np.where(dose <= d0_gy, v_total, 0.0)

    g = gradient_gy_per_mm
    h = height_mm

    # z_D is the z position where D(z) = D
    z_d = np.clip((dose - d0_gy) / g, 0.0, h)
    frac = z_d / h

    if g > 0:
        # Apex at low-dose end: subtract small cone from apex to z_D
        result = v_total * (1.0 - frac**3)
    else:
        # Apex at high-dose end: keep small cone from apex to z_D
        result = v_total * frac**3

    return np.clip(result, 0.0, v_total)


def sphere_radial_gaussian_dvh(
    dose_gy: npt.ArrayLike,
    radius_mm: float,
    amplitude_gy: float,
    sigma_mm: float,
) -> npt.NDArray[np.float64]:
    """Cumulative DVH for a sphere in a radial Gaussian dose field.

    Sphere centred at the field origin.
    Dose field D(r) = A * exp(-r^2 / (2*sigma^2)).

    This is the Stanley [17] / Walker [21] benchmark model for small
    stereotactic targets.

    Parameters
    ----------
    dose_gy : array_like
        Dose threshold(s) in Gy.
    radius_mm : float
        Sphere radius in mm. Must be > 0.
    amplitude_gy : float
        Peak dose at centre in Gy. Must be > 0.
    sigma_mm : float
        Gaussian width (standard deviation) in mm. Must be > 0.

    Returns
    -------
    NDArray[np.float64]
        Cumulative volume V(D) in mm³.
    """
    _validate_positive(
        radius_mm=radius_mm, amplitude_gy=amplitude_gy, sigma_mm=sigma_mm
    )
    dose = np.atleast_1d(np.asarray(dose_gy, dtype=np.float64))
    v_total = sphere_volume(radius_mm)

    # r(D) = sigma * sqrt(2 * ln(A/D)), valid when 0 < D <= A
    # For D > A: no volume receives that dose → V = 0
    # For D <= 0: all volume → V = V_total
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = amplitude_gy / dose
        # Only compute sqrt where ratio > 1 (i.e., D < A and D > 0)
        valid = (dose > 0) & (dose < amplitude_gy)
        r_d = np.where(
            valid,
            sigma_mm * np.sqrt(2.0 * np.log(np.where(valid, ratio, 1.0))),
            np.where(dose <= 0, radius_mm, 0.0),
        )

    # Cap at sphere radius
    r_d = np.minimum(r_d, radius_mm)

    result = (4.0 / 3.0) * np.pi * r_d**3
    return np.clip(result, 0.0, v_total)
