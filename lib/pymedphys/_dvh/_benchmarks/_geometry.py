"""Analytical volume formulas for benchmark shapes.

Provides closed-form volume calculations for the geometric primitives
used in the Tier 1 analytical benchmark suite. All inputs are in mm,
all outputs are in mm³.

These formulas provide ground-truth volumes for validating the
voxelisation engine and DVH computation pipeline.

See RFC §8.1.1, §8.1.2, and §9 Task 1.1.

References
----------
.. [14] Nelms et al., "Variation in external beam treatment plan quality:
   An inter-institutional study of planners and planning systems"
"""

from __future__ import annotations

import numpy as np

MM3_PER_CC: float = 1000.0
"""Conversion factor: 1 cc = 1000 mm³."""


def _validate_positive(**kwargs: float | np.ndarray) -> None:
    """Validate that all named arguments are strictly positive and finite.

    Parameters
    ----------
    **kwargs : float | numpy.ndarray
        Named dimension values to validate. Each value may be a scalar
        or an array-like object; all elements must be finite and
        strictly positive.

    Raises
    ------
    ValueError
        If any value is NaN, +Inf, -Inf, or not strictly positive (> 0).
    """
    for name, value in kwargs.items():
        array_value = np.asarray(value)
        if not np.all(np.isfinite(array_value)):
            raise ValueError(f"{name} must be finite, got {value}")
        if np.any(array_value <= 0):
            raise ValueError(f"{name} must be strictly positive, got {value}")


def sphere_volume(radius_mm: float) -> float:
    """Volume of a sphere.

    Parameters
    ----------
    radius_mm : float
        Radius in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``(4/3) * π * r³``.
    """
    _validate_positive(radius_mm=radius_mm)
    return (4.0 / 3.0) * np.pi * radius_mm**3


def cylinder_volume(radius_mm: float, height_mm: float) -> float:
    """Volume of a right circular cylinder.

    Parameters
    ----------
    radius_mm : float
        Base radius in mm. Must be > 0.
    height_mm : float
        Height in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``π * r² * h``.
    """
    _validate_positive(radius_mm=radius_mm, height_mm=height_mm)
    return np.pi * radius_mm**2 * height_mm


def cone_volume(radius_mm: float, height_mm: float) -> float:
    """Volume of a right circular cone.

    Parameters
    ----------
    radius_mm : float
        Base radius in mm. Must be > 0.
    height_mm : float
        Height in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``(1/3) * π * r² * h``.
    """
    _validate_positive(radius_mm=radius_mm, height_mm=height_mm)
    return (1.0 / 3.0) * np.pi * radius_mm**2 * height_mm


def ellipsoid_volume(semi_a_mm: float, semi_b_mm: float, semi_c_mm: float) -> float:
    """Volume of an ellipsoid.

    Parameters
    ----------
    semi_a_mm : float
        Semi-axis a in mm. Must be > 0.
    semi_b_mm : float
        Semi-axis b in mm. Must be > 0.
    semi_c_mm : float
        Semi-axis c in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``(4/3) * π * a * b * c``.
    """
    _validate_positive(semi_a_mm=semi_a_mm, semi_b_mm=semi_b_mm, semi_c_mm=semi_c_mm)
    return (4.0 / 3.0) * np.pi * semi_a_mm * semi_b_mm * semi_c_mm


def torus_volume(major_radius_mm: float, minor_radius_mm: float) -> float:
    """Volume of a torus.

    Parameters
    ----------
    major_radius_mm : float
        Distance from torus centre to tube centre, in mm. Must be > 0.
    minor_radius_mm : float
        Tube radius in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``2 * π² * R * r²``.
    """
    _validate_positive(major_radius_mm=major_radius_mm, minor_radius_mm=minor_radius_mm)
    return 2.0 * np.pi**2 * major_radius_mm * minor_radius_mm**2


def cylindrical_shell_volume(
    outer_radius_mm: float, inner_radius_mm: float, height_mm: float
) -> float:
    """Volume of a thin cylindrical shell (hollow cylinder).

    Parameters
    ----------
    outer_radius_mm : float
        Outer radius in mm. Must be > 0.
    inner_radius_mm : float
        Inner radius in mm. Must be > 0.
    height_mm : float
        Height in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``π * (R² - r²) * h``.

    Raises
    ------
    ValueError
        If outer_radius_mm <= inner_radius_mm.
    """
    _validate_positive(
        outer_radius_mm=outer_radius_mm,
        inner_radius_mm=inner_radius_mm,
        height_mm=height_mm,
    )
    if outer_radius_mm <= inner_radius_mm:
        raise ValueError(
            f"outer_radius_mm ({outer_radius_mm}) must be strictly greater "
            f"than inner_radius_mm ({inner_radius_mm})"
        )
    return np.pi * (outer_radius_mm**2 - inner_radius_mm**2) * height_mm


def rectangular_parallelepiped_volume(
    length_mm: float, width_mm: float, height_mm: float
) -> float:
    """Volume of a rectangular parallelepiped (box).

    Parameters
    ----------
    length_mm : float
        Length in mm. Must be > 0.
    width_mm : float
        Width in mm. Must be > 0.
    height_mm : float
        Height in mm. Must be > 0.

    Returns
    -------
    float
        Volume in mm³: ``l * w * h``.
    """
    _validate_positive(length_mm=length_mm, width_mm=width_mm, height_mm=height_mm)
    return length_mm * width_mm * height_mm


def mm3_to_cc(volume_mm3: float) -> float:
    """Convert volume from mm³ to cubic centimetres (cc / mL).

    Parameters
    ----------
    volume_mm3 : float
        Volume in mm³.

    Returns
    -------
    float
        Volume in cc (1 cc = 1000 mm³).
    """
    return volume_mm3 / MM3_PER_CC
