"""Orthogonal 3D dense-grid volume-estimate cross-checks.

These tests provide an independent numerical sanity check against the
analytical DVH formulas by directly sampling dose on a dense 3D Cartesian
grid. This is methodologically orthogonal to the quad-based numerical
integration tests in test_dvh_analytical.py:

- The quad tests integrate 1D cross-sections — they share the same
  coordinate-reduction logic as the analytical code (z-axis slicing,
  cap-height → volume mapping).
- These dense-grid tests evaluate dose at every voxel in a 3D grid, count
  voxels where dose >= threshold, and multiply by voxel volume. This uses
  no analytical geometry at all — only point-in-shape tests and raw dose
  evaluation — so it catches common-mode errors in coordinate conventions,
  threshold equations (z_cut, r_crit), or cap-height formulas.

The trade-off is speed: these tests are ~100× slower than the quad tests,
so we use one representative parameter set per shape×dose combination.

See RFC §9 Task 1.2 and §8.1.1.
"""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._benchmarks._dvh_analytical import (
    cone_linear_gradient_dvh,
    cylinder_linear_gradient_dvh,
    sphere_linear_gradient_dvh,
    sphere_radial_gaussian_dvh,
)
from pymedphys._dvh._benchmarks._geometry import sphere_volume


# ---------------------------------------------------------------------------
# Dense-grid DVH estimators
# ---------------------------------------------------------------------------


def _dense_grid_dvh_symmetric(
    dose_threshold: float,
    extent: tuple[float, float, float],
    n_per_axis: int,
    point_in_shape: callable,
    dose_at_point: callable,
) -> float:
    """Estimate V(D) by brute-force 3D voxel counting on a symmetric grid.

    Grid spans [-extent, +extent] on each axis.
    """
    ex, ey, ez = extent
    x = np.linspace(-ex, ex, n_per_axis)
    y = np.linspace(-ey, ey, n_per_axis)
    z = np.linspace(-ez, ez, n_per_axis)
    voxel_vol = (
        (2.0 * ex / (n_per_axis - 1))
        * (2.0 * ey / (n_per_axis - 1))
        * (2.0 * ez / (n_per_axis - 1))
    )

    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    inside = point_in_shape(X, Y, Z)
    dose = dose_at_point(X, Y, Z)
    return float(np.sum(inside & (dose >= dose_threshold))) * voxel_vol


def _dense_grid_dvh_ranged(
    dose_threshold: float,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    z_range: tuple[float, float],
    n_per_axis: int,
    point_in_shape: callable,
    dose_at_point: callable,
) -> float:
    """Estimate V(D) by brute-force 3D voxel counting with explicit ranges.

    Used for shapes not centred at origin (cylinder/cone with base at z=0).
    """
    x = np.linspace(x_range[0], x_range[1], n_per_axis)
    y = np.linspace(y_range[0], y_range[1], n_per_axis)
    z = np.linspace(z_range[0], z_range[1], n_per_axis)
    voxel_vol = (
        (x_range[1] - x_range[0])
        / (n_per_axis - 1)
        * (y_range[1] - y_range[0])
        / (n_per_axis - 1)
        * (z_range[1] - z_range[0])
        / (n_per_axis - 1)
    )

    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    inside = point_in_shape(X, Y, Z)
    dose = dose_at_point(X, Y, Z)
    return float(np.sum(inside & (dose >= dose_threshold))) * voxel_vol


# ---------------------------------------------------------------------------
# Shape membership functions (pure 3D point-in-shape tests)
# ---------------------------------------------------------------------------


def _in_sphere(radius: float):
    def test(x, y, z):
        return x**2 + y**2 + z**2 <= radius**2

    return test


def _in_cylinder(radius: float, height: float):
    """Cylinder with base at z=0, top at z=height, centred on z-axis."""

    def test(x, y, z):
        return (x**2 + y**2 <= radius**2) & (z >= 0) & (z <= height)

    return test


def _in_cone(base_radius: float, height: float):
    """Cone with apex at z=0, base at z=height."""

    def test(x, y, z):
        r_at_z = base_radius * np.maximum(z, 0.0) / height
        return (x**2 + y**2 <= r_at_z**2) & (z >= 0) & (z <= height)

    return test


# ---------------------------------------------------------------------------
# Dose field functions for 3D grids
# ---------------------------------------------------------------------------


def _linear_dose_z(d0: float, g: float):
    """D(x,y,z) = d0 + g*z."""

    def dose(x, y, z):
        return d0 + g * z

    return dose


def _radial_gaussian_dose_3d(amplitude: float, sigma: float):
    """D(x,y,z) = A * exp(-r²/(2σ²)) where r = sqrt(x²+y²+z²)."""

    def dose(x, y, z):
        r2 = x**2 + y**2 + z**2
        return amplitude * np.exp(-r2 / (2.0 * sigma**2))

    return dose


# ---------------------------------------------------------------------------
# Tests: one representative case per shape×dose combination
# ---------------------------------------------------------------------------

# 201³ ≈ 8M points. At this resolution, boundary voxels (partially
# inside the shape) dominate the error, giving ~2-3% accuracy.
N = 201
RTOL = 0.03  # 3% relative tolerance for grid-based estimates


class TestDenseGridSphereLinearGradient:
    """3D grid cross-check for sphere + linear gradient DVH."""

    R, D0, G = 10.0, 50.0, 1.0

    @pytest.mark.parametrize(
        "dose_frac",
        [0.25, 0.50, 0.75],
        ids=["quarter", "midpoint", "three-quarter"],
    )
    def test_volume_agrees_with_analytical(self, dose_frac: float) -> None:
        d_min = self.D0 - abs(self.G) * self.R
        d_max = self.D0 + abs(self.G) * self.R
        dose = d_min + dose_frac * (d_max - d_min)

        analytical = float(sphere_linear_gradient_dvh(dose, self.R, self.D0, self.G)[0])
        numerical = _dense_grid_dvh_symmetric(
            dose,
            extent=(self.R, self.R, self.R),
            n_per_axis=N,
            point_in_shape=_in_sphere(self.R),
            dose_at_point=_linear_dose_z(self.D0, self.G),
        )
        assert numerical == pytest.approx(analytical, rel=RTOL), (
            f"Dense-grid V({dose:.1f} Gy) = {numerical:.1f} mm³, "
            f"analytical = {analytical:.1f} mm³"
        )

    def test_total_volume_at_dmin(self) -> None:
        """Near Dmin, almost all sphere volume should qualify."""
        d_min = self.D0 - abs(self.G) * self.R
        numerical = _dense_grid_dvh_symmetric(
            d_min + 0.01,
            extent=(self.R, self.R, self.R),
            n_per_axis=N,
            point_in_shape=_in_sphere(self.R),
            dose_at_point=_linear_dose_z(self.D0, self.G),
        )
        assert numerical == pytest.approx(sphere_volume(self.R), rel=RTOL)


class TestDenseGridCylinderLinearGradient:
    """3D grid cross-check for cylinder + linear gradient DVH."""

    R, H, D0, G = 12.0, 24.0, 30.0, 1.0

    @pytest.mark.parametrize(
        "dose_frac",
        [0.25, 0.50, 0.75],
        ids=["quarter", "midpoint", "three-quarter"],
    )
    def test_volume_agrees_with_analytical(self, dose_frac: float) -> None:
        d_min = min(self.D0, self.D0 + self.G * self.H)
        d_max = max(self.D0, self.D0 + self.G * self.H)
        dose = d_min + dose_frac * (d_max - d_min)

        analytical = float(
            cylinder_linear_gradient_dvh(dose, self.R, self.H, self.D0, self.G)[0]
        )
        numerical = _dense_grid_dvh_ranged(
            dose,
            x_range=(-self.R, self.R),
            y_range=(-self.R, self.R),
            z_range=(0.0, self.H),
            n_per_axis=N,
            point_in_shape=_in_cylinder(self.R, self.H),
            dose_at_point=_linear_dose_z(self.D0, self.G),
        )
        assert numerical == pytest.approx(analytical, rel=RTOL), (
            f"Dense-grid V({dose:.1f} Gy) = {numerical:.1f} mm³, "
            f"analytical = {analytical:.1f} mm³"
        )


class TestDenseGridConeLinearGradient:
    """3D grid cross-check for cone + linear gradient DVH."""

    R, H, D0, G = 12.0, 24.0, 30.0, 1.0

    @pytest.mark.parametrize(
        "dose_frac",
        [0.25, 0.50, 0.75],
        ids=["quarter", "midpoint", "three-quarter"],
    )
    def test_volume_agrees_with_analytical(self, dose_frac: float) -> None:
        d_min = min(self.D0, self.D0 + self.G * self.H)
        d_max = max(self.D0, self.D0 + self.G * self.H)
        dose = d_min + dose_frac * (d_max - d_min)

        analytical = float(
            cone_linear_gradient_dvh(dose, self.R, self.H, self.D0, self.G)[0]
        )
        numerical = _dense_grid_dvh_ranged(
            dose,
            x_range=(-self.R, self.R),
            y_range=(-self.R, self.R),
            z_range=(0.0, self.H),
            n_per_axis=N,
            point_in_shape=_in_cone(self.R, self.H),
            dose_at_point=_linear_dose_z(self.D0, self.G),
        )
        assert numerical == pytest.approx(analytical, rel=RTOL), (
            f"Dense-grid V({dose:.1f} Gy) = {numerical:.1f} mm³, "
            f"analytical = {analytical:.1f} mm³"
        )


class TestDenseGridSphereRadialGaussian:
    """3D grid cross-check for sphere + radial Gaussian DVH."""

    R, A, SIGMA = 10.0, 60.0, 10.0

    @pytest.mark.parametrize(
        "dose_frac",
        [0.25, 0.50, 0.75],
        ids=["quarter", "midpoint", "three-quarter"],
    )
    def test_volume_agrees_with_analytical(self, dose_frac: float) -> None:
        d_surface = self.A * np.exp(-(self.R**2) / (2.0 * self.SIGMA**2))
        dose = d_surface + dose_frac * (self.A - d_surface)

        analytical = float(
            sphere_radial_gaussian_dvh(dose, self.R, self.A, self.SIGMA)[0]
        )
        numerical = _dense_grid_dvh_symmetric(
            dose,
            extent=(self.R, self.R, self.R),
            n_per_axis=N,
            point_in_shape=_in_sphere(self.R),
            dose_at_point=_radial_gaussian_dose_3d(self.A, self.SIGMA),
        )
        assert numerical == pytest.approx(analytical, rel=RTOL), (
            f"Dense-grid V({dose:.1f} Gy) = {numerical:.1f} mm³, "
            f"analytical = {analytical:.1f} mm³"
        )
