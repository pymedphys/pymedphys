"""Tests for closed-form cumulative DVH formulas.

Each analytical DVH V(D) is validated against:
- Boundary values: V(Dmin) = V_total, V(Dmax) = 0
- Known intermediate values (e.g. midpoint → half volume for cylinder)
- Numerical integration via scipy.integrate.quad (< 0.01% error)
- Property-based invariants via hypothesis (monotonicity, bounds)

See RFC §9 Task 1.2 for specification.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from scipy.integrate import quad

from pymedphys._dvh._benchmarks._dvh_analytical import (
    cone_linear_gradient_dvh,
    cylinder_linear_gradient_dvh,
    sphere_linear_gradient_dvh,
    sphere_radial_gaussian_dvh,
)
from pymedphys._dvh._benchmarks._geometry import (
    cone_volume,
    cylinder_volume,
    sphere_volume,
)


# ---------------------------------------------------------------------------
# Numerical integration reference implementations
# ---------------------------------------------------------------------------


def _numerical_sphere_linear_dvh(
    dose_gy: float, radius_mm: float, d0_gy: float, g: float
) -> float:
    """Numerical V(D) for sphere in linear gradient via cross-section integration."""
    if g == 0:
        return sphere_volume(radius_mm) if dose_gy <= d0_gy else 0.0

    # Cross-section area of sphere at height z from centre: pi*(r^2 - z^2)
    def integrand(z: float) -> float:
        return np.pi * (radius_mm**2 - z**2)

    d_max = d0_gy + abs(g) * radius_mm
    d_min = d0_gy - abs(g) * radius_mm
    if dose_gy >= d_max:
        return 0.0
    if dose_gy <= d_min:
        return sphere_volume(radius_mm)
    # Region where D(z) >= dose_gy
    if g > 0:
        z_cut = (dose_gy - d0_gy) / g
        lo, hi = max(-radius_mm, z_cut), radius_mm
    else:
        z_cut = (dose_gy - d0_gy) / g
        lo, hi = -radius_mm, min(radius_mm, z_cut)
    result, _ = quad(integrand, lo, hi)
    return max(0.0, result)


def _numerical_cylinder_linear_dvh(
    dose_gy: float, radius_mm: float, height_mm: float, d0_gy: float, g: float
) -> float:
    """Numerical V(D) for cylinder in linear gradient."""
    if g == 0:
        return cylinder_volume(radius_mm, height_mm) if dose_gy <= d0_gy else 0.0
    area = np.pi * radius_mm**2
    d_at_0 = d0_gy
    d_at_h = d0_gy + g * height_mm
    d_max = max(d_at_0, d_at_h)
    d_min = min(d_at_0, d_at_h)
    if dose_gy >= d_max:
        return 0.0
    if dose_gy <= d_min:
        return cylinder_volume(radius_mm, height_mm)
    # Length of cylinder axis where dose >= dose_gy
    if g > 0:
        z_cut = (dose_gy - d0_gy) / g
        length = height_mm - max(0.0, min(z_cut, height_mm))
    else:
        z_cut = (dose_gy - d0_gy) / g
        length = min(z_cut, height_mm) - 0.0
    return max(0.0, area * length)


def _numerical_cone_linear_dvh(
    dose_gy: float, base_radius_mm: float, height_mm: float, d0_gy: float, g: float
) -> float:
    """Numerical V(D) for cone in linear gradient via cross-section integration."""
    if g == 0:
        return cone_volume(base_radius_mm, height_mm) if dose_gy <= d0_gy else 0.0

    def integrand(z: float) -> float:
        r_z = base_radius_mm * z / height_mm
        return np.pi * r_z**2

    d_at_0 = d0_gy
    d_at_h = d0_gy + g * height_mm
    d_max = max(d_at_0, d_at_h)
    d_min = min(d_at_0, d_at_h)
    if dose_gy >= d_max:
        return 0.0
    if dose_gy <= d_min:
        return cone_volume(base_radius_mm, height_mm)
    z_cut = np.clip((dose_gy - d0_gy) / g, 0.0, height_mm)
    if g > 0:
        lo, hi = z_cut, height_mm
    else:
        lo, hi = 0.0, z_cut
    result, _ = quad(integrand, lo, hi)
    return max(0.0, result)


def _numerical_sphere_gaussian_dvh(
    dose_gy: float, radius_mm: float, amplitude_gy: float, sigma_mm: float
) -> float:
    """Numerical V(D) for sphere in radial Gaussian via shell integration."""
    if dose_gy <= 0:
        return sphere_volume(radius_mm)
    if dose_gy >= amplitude_gy:
        return 0.0

    def integrand(r: float) -> float:
        d_at_r = amplitude_gy * np.exp(-(r**2) / (2.0 * sigma_mm**2))
        return 4.0 * np.pi * r**2 if d_at_r >= dose_gy else 0.0

    # Critical radius where dose = dose_gy
    r_crit = sigma_mm * np.sqrt(2.0 * np.log(amplitude_gy / dose_gy))
    r_upper = min(r_crit, radius_mm)
    result, _ = quad(integrand, 0.0, radius_mm, points=[r_upper])
    return max(0.0, result)


# ---------------------------------------------------------------------------
# Parameter sets for numerical integration (5 per formula, per RFC)
# ---------------------------------------------------------------------------

SPHERE_LINEAR_PARAMS = [
    {"radius_mm": 3.0, "d0_gy": 50.0, "gradient_gy_per_mm": 0.5},  # small SRS
    {"radius_mm": 10.0, "d0_gy": 50.0, "gradient_gy_per_mm": 1.0},  # Nelms-like
    {"radius_mm": 12.0, "d0_gy": 30.0, "gradient_gy_per_mm": 2.0},  # Nelms ref
    {"radius_mm": 30.0, "d0_gy": 60.0, "gradient_gy_per_mm": 0.1},  # large, shallow
    {"radius_mm": 10.0, "d0_gy": 50.0, "gradient_gy_per_mm": -1.0},  # negative grad
]

CYLINDER_LINEAR_PARAMS = [
    {"radius_mm": 3.0, "height_mm": 10.0, "d0_gy": 50.0, "gradient_gy_per_mm": 0.5},
    {"radius_mm": 12.0, "height_mm": 24.0, "d0_gy": 30.0, "gradient_gy_per_mm": 1.0},
    {"radius_mm": 10.0, "height_mm": 50.0, "d0_gy": 60.0, "gradient_gy_per_mm": 0.01},
    {"radius_mm": 5.0, "height_mm": 20.0, "d0_gy": 40.0, "gradient_gy_per_mm": 2.0},
    {"radius_mm": 12.0, "height_mm": 24.0, "d0_gy": 60.0, "gradient_gy_per_mm": -1.0},
]

CONE_LINEAR_PARAMS = [
    {
        "base_radius_mm": 3.0,
        "height_mm": 10.0,
        "d0_gy": 50.0,
        "gradient_gy_per_mm": 0.5,
    },
    {
        "base_radius_mm": 12.0,
        "height_mm": 24.0,
        "d0_gy": 30.0,
        "gradient_gy_per_mm": 1.0,
    },
    {
        "base_radius_mm": 10.0,
        "height_mm": 50.0,
        "d0_gy": 60.0,
        "gradient_gy_per_mm": 0.01,
    },
    {
        "base_radius_mm": 5.0,
        "height_mm": 20.0,
        "d0_gy": 40.0,
        "gradient_gy_per_mm": 2.0,
    },
    {
        "base_radius_mm": 12.0,
        "height_mm": 24.0,
        "d0_gy": 60.0,
        "gradient_gy_per_mm": -1.0,
    },
]

GAUSSIAN_PARAMS = [
    {"radius_mm": 3.0, "amplitude_gy": 60.0, "sigma_mm": 5.0},
    {"radius_mm": 10.0, "amplitude_gy": 60.0, "sigma_mm": 10.0},
    {"radius_mm": 30.0, "amplitude_gy": 80.0, "sigma_mm": 20.0},
    {"radius_mm": 5.0, "amplitude_gy": 100.0, "sigma_mm": 3.0},
    {"radius_mm": 15.0, "amplitude_gy": 50.0, "sigma_mm": 50.0},  # broad Gaussian
]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestSphereLinearGradientDVH:
    """Tests for sphere_linear_gradient_dvh."""

    def test_uniform_dose_full_volume_below(self) -> None:
        """g=0, D < D₀ → V = V_total."""
        v = sphere_linear_gradient_dvh(
            40.0, radius_mm=10.0, d0_gy=50.0, gradient_gy_per_mm=0.0
        )
        assert float(v[0]) == pytest.approx(sphere_volume(10.0), rel=1e-10)

    def test_uniform_dose_zero_above(self) -> None:
        """g=0, D > D₀ → V = 0."""
        v = sphere_linear_gradient_dvh(
            60.0, radius_mm=10.0, d0_gy=50.0, gradient_gy_per_mm=0.0
        )
        assert float(v[0]) == pytest.approx(0.0, abs=1e-15)

    def test_dmin_gives_total_volume(self) -> None:
        """V(Dmin) = V_total."""
        r, d0, g = 10.0, 50.0, 1.0
        d_min = d0 - abs(g) * r
        v = sphere_linear_gradient_dvh(d_min, r, d0, g)
        assert float(v[0]) == pytest.approx(sphere_volume(r), rel=1e-10)

    def test_dmax_gives_zero(self) -> None:
        """V(Dmax) = 0."""
        r, d0, g = 10.0, 50.0, 1.0
        d_max = d0 + abs(g) * r
        v = sphere_linear_gradient_dvh(d_max, r, d0, g)
        assert float(v[0]) == pytest.approx(0.0, abs=1e-10)

    def test_midpoint_gives_half_volume(self) -> None:
        """V(D₀) = V_total/2 by symmetry of sphere about its centre."""
        r, d0, g = 10.0, 50.0, 1.0
        v = sphere_linear_gradient_dvh(d0, r, d0, g)
        assert float(v[0]) == pytest.approx(sphere_volume(r) / 2.0, rel=1e-10)

    def test_negative_gradient(self) -> None:
        """Negative gradient: V(Dmin) = V_total, V(Dmax) = 0."""
        r, d0, g = 10.0, 50.0, -1.0
        d_max = d0 + abs(g) * r
        d_min = d0 - abs(g) * r
        v_min = sphere_linear_gradient_dvh(d_min, r, d0, g)
        v_max = sphere_linear_gradient_dvh(d_max, r, d0, g)
        assert float(v_min[0]) == pytest.approx(sphere_volume(r), rel=1e-10)
        assert float(v_max[0]) == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.parametrize("params", SPHERE_LINEAR_PARAMS)
    def test_agrees_with_numerical_integration(self, params: dict) -> None:
        """Analytical formula matches quad() to < 0.01%."""
        r = params["radius_mm"]
        d0 = params["d0_gy"]
        g = params["gradient_gy_per_mm"]
        d_max = d0 + abs(g) * r
        d_min = d0 - abs(g) * r
        doses = np.linspace(d_min, d_max, 50)
        analytical = sphere_linear_gradient_dvh(doses, r, d0, g)
        for i, d in enumerate(doses):
            numerical = _numerical_sphere_linear_dvh(d, r, d0, g)
            if numerical > 1e-6:
                assert float(analytical[i]) == pytest.approx(numerical, rel=1e-4), (
                    f"Mismatch at D={d:.2f} Gy"
                )

    @given(
        dose_frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_bounded_zero_to_total(self, dose_frac: float) -> None:
        """0 ≤ V(D) ≤ V_total for all D in [Dmin, Dmax]."""
        r, d0, g = 10.0, 50.0, 1.0
        d_min = d0 - abs(g) * r
        d_max = d0 + abs(g) * r
        d = d_min + dose_frac * (d_max - d_min)
        v = float(sphere_linear_gradient_dvh(d, r, d0, g)[0])
        assert -1e-10 <= v <= sphere_volume(r) + 1e-10

    def test_monotonically_nonincreasing(self) -> None:
        """V(D) is non-increasing in D."""
        r, d0, g = 10.0, 50.0, 1.0
        d_min = d0 - abs(g) * r
        d_max = d0 + abs(g) * r
        doses = np.linspace(d_min, d_max, 200)
        volumes = sphere_linear_gradient_dvh(doses, r, d0, g)
        diffs = np.diff(volumes)
        assert np.all(diffs <= 1e-10), "DVH must be non-increasing"

    def test_vectorized_input(self) -> None:
        """Array input returns correct shape."""
        doses = np.array([40.0, 50.0, 60.0])
        result = sphere_linear_gradient_dvh(
            doses, radius_mm=10.0, d0_gy=50.0, gradient_gy_per_mm=1.0
        )
        assert result.shape == (3,)

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            sphere_linear_gradient_dvh(
                50.0, radius_mm=0.0, d0_gy=50.0, gradient_gy_per_mm=1.0
            )


class TestCylinderLinearGradientDVH:
    """Tests for cylinder_linear_gradient_dvh."""

    def test_midpoint_dose_half_volume(self) -> None:
        """Cylinder has constant cross-section: V(midpoint) = V_total/2."""
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_mid = d0 + g * h / 2.0
        v = cylinder_linear_gradient_dvh(d_mid, r, h, d0, g)
        assert float(v[0]) == pytest.approx(cylinder_volume(r, h) / 2.0, rel=1e-10)

    def test_dmin_gives_total_volume(self) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        v = cylinder_linear_gradient_dvh(d0, r, h, d0, g)
        assert float(v[0]) == pytest.approx(cylinder_volume(r, h), rel=1e-10)

    def test_dmax_gives_zero(self) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_max = d0 + g * h
        v = cylinder_linear_gradient_dvh(d_max, r, h, d0, g)
        assert float(v[0]) == pytest.approx(0.0, abs=1e-10)

    def test_uniform_dose_step_function(self) -> None:
        """g=0: step function at D₀."""
        r, h, d0 = 12.0, 24.0, 50.0
        v_below = cylinder_linear_gradient_dvh(40.0, r, h, d0, 0.0)
        v_above = cylinder_linear_gradient_dvh(60.0, r, h, d0, 0.0)
        assert float(v_below[0]) == pytest.approx(cylinder_volume(r, h), rel=1e-10)
        assert float(v_above[0]) == pytest.approx(0.0, abs=1e-15)

    @pytest.mark.parametrize("params", CYLINDER_LINEAR_PARAMS)
    def test_agrees_with_numerical_integration(self, params: dict) -> None:
        r = params["radius_mm"]
        h = params["height_mm"]
        d0 = params["d0_gy"]
        g = params["gradient_gy_per_mm"]
        d_max = max(d0, d0 + g * h)
        d_min = min(d0, d0 + g * h)
        doses = np.linspace(d_min, d_max, 50)
        analytical = cylinder_linear_gradient_dvh(doses, r, h, d0, g)
        for i, d in enumerate(doses):
            numerical = _numerical_cylinder_linear_dvh(d, r, h, d0, g)
            if numerical > 1e-6:
                assert float(analytical[i]) == pytest.approx(numerical, rel=1e-4), (
                    f"Mismatch at D={d:.2f} Gy"
                )

    @given(dose_frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=50)
    def test_bounded(self, dose_frac: float) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_min = d0
        d_max = d0 + g * h
        d = d_min + dose_frac * (d_max - d_min)
        v = float(cylinder_linear_gradient_dvh(d, r, h, d0, g)[0])
        assert -1e-10 <= v <= cylinder_volume(r, h) + 1e-10

    def test_monotonically_nonincreasing(self) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        doses = np.linspace(d0, d0 + g * h, 200)
        volumes = cylinder_linear_gradient_dvh(doses, r, h, d0, g)
        assert np.all(np.diff(volumes) <= 1e-10)

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            cylinder_linear_gradient_dvh(50.0, 0.0, 24.0, 30.0, 1.0)


class TestConeLinearGradientDVH:
    """Tests for cone_linear_gradient_dvh."""

    def test_dmin_gives_total_volume(self) -> None:
        """V(Dmin) = V_total for cone."""
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        v = cone_linear_gradient_dvh(d0, r, h, d0, g)
        assert float(v[0]) == pytest.approx(cone_volume(r, h), rel=1e-10)

    def test_dmax_gives_zero(self) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_max = d0 + g * h
        v = cone_linear_gradient_dvh(d_max, r, h, d0, g)
        assert float(v[0]) == pytest.approx(0.0, abs=1e-10)

    def test_half_height_dose_positive_gradient(self) -> None:
        """g>0, apex at z=0: V(D at z=H/2) = V_total*(1 - 0.5³) = 0.875*V_total."""
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_half = d0 + g * h / 2.0  # dose at z = H/2
        v = cone_linear_gradient_dvh(d_half, r, h, d0, g)
        assert float(v[0]) == pytest.approx(
            cone_volume(r, h) * (1.0 - 0.5**3), rel=1e-10
        )

    def test_quarter_height_dose_positive_gradient(self) -> None:
        """g>0: V(D at z=H/4) = V_total*(1 - 0.25³) = 0.984375*V_total."""
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_quarter = d0 + g * h / 4.0
        v = cone_linear_gradient_dvh(d_quarter, r, h, d0, g)
        assert float(v[0]) == pytest.approx(
            cone_volume(r, h) * (1.0 - 0.25**3), rel=1e-10
        )

    def test_negative_gradient(self) -> None:
        """g<0: apex at high-dose end. V(D at z=H/2) = V_total*0.5³ = 0.125*V_total."""
        r, h, d0, g = 12.0, 24.0, 60.0, -1.0
        d_half = d0 + g * h / 2.0  # dose at z = H/2
        v = cone_linear_gradient_dvh(d_half, r, h, d0, g)
        assert float(v[0]) == pytest.approx(cone_volume(r, h) * 0.5**3, rel=1e-10)

    def test_uniform_dose_step_function(self) -> None:
        r, h, d0 = 12.0, 24.0, 50.0
        v_below = cone_linear_gradient_dvh(40.0, r, h, d0, 0.0)
        v_above = cone_linear_gradient_dvh(60.0, r, h, d0, 0.0)
        assert float(v_below[0]) == pytest.approx(cone_volume(r, h), rel=1e-10)
        assert float(v_above[0]) == pytest.approx(0.0, abs=1e-15)

    @pytest.mark.parametrize("params", CONE_LINEAR_PARAMS)
    def test_agrees_with_numerical_integration(self, params: dict) -> None:
        r = params["base_radius_mm"]
        h = params["height_mm"]
        d0 = params["d0_gy"]
        g = params["gradient_gy_per_mm"]
        d_max = max(d0, d0 + g * h)
        d_min = min(d0, d0 + g * h)
        doses = np.linspace(d_min, d_max, 50)
        analytical = cone_linear_gradient_dvh(doses, r, h, d0, g)
        for i, d in enumerate(doses):
            numerical = _numerical_cone_linear_dvh(d, r, h, d0, g)
            if numerical > 1e-6:
                assert float(analytical[i]) == pytest.approx(numerical, rel=1e-4), (
                    f"Mismatch at D={d:.2f} Gy"
                )

    @given(dose_frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=50)
    def test_bounded(self, dose_frac: float) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        d_min = d0
        d_max = d0 + g * h
        d = d_min + dose_frac * (d_max - d_min)
        v = float(cone_linear_gradient_dvh(d, r, h, d0, g)[0])
        assert -1e-10 <= v <= cone_volume(r, h) + 1e-10

    def test_monotonically_nonincreasing(self) -> None:
        r, h, d0, g = 12.0, 24.0, 30.0, 1.0
        doses = np.linspace(d0, d0 + g * h, 200)
        volumes = cone_linear_gradient_dvh(doses, r, h, d0, g)
        assert np.all(np.diff(volumes) <= 1e-10)

    def test_rejects_zero_height(self) -> None:
        with pytest.raises(ValueError, match="height_mm"):
            cone_linear_gradient_dvh(50.0, 12.0, 0.0, 30.0, 1.0)


class TestSphereRadialGaussianDVH:
    """Tests for sphere_radial_gaussian_dvh."""

    def test_dose_below_surface_gives_total_volume(self) -> None:
        """When D ≤ dose at sphere surface, V = V_total."""
        r, A, sigma = 10.0, 60.0, 10.0
        d_surface = A * np.exp(-(r**2) / (2.0 * sigma**2))
        v = sphere_radial_gaussian_dvh(d_surface * 0.99, r, A, sigma)
        assert float(v[0]) == pytest.approx(sphere_volume(r), rel=1e-6)

    def test_peak_dose_gives_zero(self) -> None:
        """V(A) = 0 (only the centre point receives dose A)."""
        v = sphere_radial_gaussian_dvh(
            60.0, radius_mm=10.0, amplitude_gy=60.0, sigma_mm=10.0
        )
        assert float(v[0]) == pytest.approx(0.0, abs=1e-10)

    def test_above_peak_gives_zero(self) -> None:
        """V(D > A) = 0."""
        v = sphere_radial_gaussian_dvh(
            70.0, radius_mm=10.0, amplitude_gy=60.0, sigma_mm=10.0
        )
        assert float(v[0]) == pytest.approx(0.0, abs=1e-10)

    def test_half_amplitude_known_radius(self) -> None:
        """At D = A/2: r(D) = σ√(2·ln(2)), V = (4π/3)·r(D)³ if r(D) < R."""
        A, sigma, R = 60.0, 10.0, 30.0
        r_d = sigma * np.sqrt(2.0 * np.log(2.0))
        expected = (4.0 / 3.0) * np.pi * r_d**3
        v = sphere_radial_gaussian_dvh(A / 2.0, R, A, sigma)
        assert float(v[0]) == pytest.approx(expected, rel=1e-10)

    @pytest.mark.parametrize("params", GAUSSIAN_PARAMS)
    def test_agrees_with_numerical_integration(self, params: dict) -> None:
        r = params["radius_mm"]
        A = params["amplitude_gy"]
        sigma = params["sigma_mm"]
        d_surface = A * np.exp(-(r**2) / (2.0 * sigma**2))
        doses = np.linspace(d_surface * 0.5, A * 0.99, 30)
        analytical = sphere_radial_gaussian_dvh(doses, r, A, sigma)
        for i, d in enumerate(doses):
            numerical = _numerical_sphere_gaussian_dvh(d, r, A, sigma)
            if numerical > 1e-6:
                assert float(analytical[i]) == pytest.approx(numerical, rel=1e-4), (
                    f"Mismatch at D={d:.2f} Gy"
                )

    @given(dose_frac=st.floats(min_value=0.01, max_value=0.99, allow_nan=False))
    @settings(max_examples=50)
    def test_bounded(self, dose_frac: float) -> None:
        r, A, sigma = 10.0, 60.0, 10.0
        d = dose_frac * A
        v = float(sphere_radial_gaussian_dvh(d, r, A, sigma)[0])
        assert -1e-10 <= v <= sphere_volume(r) + 1e-10

    def test_monotonically_nonincreasing(self) -> None:
        r, A, sigma = 10.0, 60.0, 10.0
        doses = np.linspace(1.0, A - 0.1, 200)
        volumes = sphere_radial_gaussian_dvh(doses, r, A, sigma)
        assert np.all(np.diff(volumes) <= 1e-10)

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            sphere_radial_gaussian_dvh(30.0, 0.0, 60.0, 10.0)

    def test_rejects_negative_amplitude(self) -> None:
        with pytest.raises(ValueError, match="amplitude_gy"):
            sphere_radial_gaussian_dvh(30.0, 10.0, -60.0, 10.0)

    def test_rejects_zero_sigma(self) -> None:
        with pytest.raises(ValueError, match="sigma_mm"):
            sphere_radial_gaussian_dvh(30.0, 10.0, 60.0, 0.0)
