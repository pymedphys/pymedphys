"""Tests for analytical geometry volume formulas.

Each shape's volume formula is verified against at least 3 hand-calculated
values, including reference values from Nelms et al. [14] where available.

See RFC §8.1.1 and §9 Task 1.1 for specification.
"""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._benchmarks._geometry import (
    MM3_PER_CC,
    cone_volume,
    cylinder_volume,
    cylindrical_shell_volume,
    ellipsoid_volume,
    mm3_to_cc,
    rectangular_parallelepiped_volume,
    sphere_volume,
    torus_volume,
)


class TestSphereVolume:
    """Tests for sphere_volume(radius_mm) = (4/3)πr³."""

    def test_r10_hand_calculation(self) -> None:
        """Sphere r=10mm: V = 4188.79 mm³ (RFC §9 Task 1.1)."""
        assert sphere_volume(10.0) == pytest.approx(4188.79, abs=0.01)

    def test_r1_unit_sphere(self) -> None:
        """Unit sphere: V = 4π/3 mm³."""
        assert sphere_volume(1.0) == pytest.approx(4.0 * np.pi / 3.0, rel=1e-12)

    def test_r12(self) -> None:
        """Sphere r=12mm: V = (4/3)π(12)³ = 7238.23 mm³."""
        expected = (4.0 / 3.0) * np.pi * 12.0**3
        assert sphere_volume(12.0) == pytest.approx(expected, rel=1e-12)

    def test_r10_in_cc(self) -> None:
        """Sphere r=10mm: V = 4.189 cc (RFC §9 Task 1.1)."""
        assert mm3_to_cc(sphere_volume(10.0)) == pytest.approx(4.189, abs=0.001)

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            sphere_volume(0.0)

    def test_rejects_negative_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            sphere_volume(-5.0)


class TestCylinderVolume:
    """Tests for cylinder_volume(radius_mm, height_mm) = πr²h."""

    def test_r12_h24_nelms_reference(self) -> None:
        """Cylinder r=12mm, h=24mm: V = 10857.34 mm³ (Nelms et al. [14])."""
        assert cylinder_volume(12.0, 24.0) == pytest.approx(10857.34, abs=0.01)

    def test_r1_h1(self) -> None:
        """Unit cylinder: V = π mm³."""
        assert cylinder_volume(1.0, 1.0) == pytest.approx(np.pi, rel=1e-12)

    def test_r5_h10(self) -> None:
        """Cylinder r=5mm, h=10mm: V = π(25)(10) = 785.398 mm³."""
        expected = np.pi * 25.0 * 10.0
        assert cylinder_volume(5.0, 10.0) == pytest.approx(expected, rel=1e-12)

    def test_r12_h24_in_cc(self) -> None:
        """Cylinder r=12mm, h=24mm: V = 10.857 cc (Nelms et al. [14])."""
        assert mm3_to_cc(cylinder_volume(12.0, 24.0)) == pytest.approx(
            10.857, abs=0.001
        )

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            cylinder_volume(0.0, 10.0)

    def test_rejects_negative_height(self) -> None:
        with pytest.raises(ValueError, match="height_mm"):
            cylinder_volume(5.0, -1.0)


class TestConeVolume:
    """Tests for cone_volume(radius_mm, height_mm) = (1/3)πr²h."""

    def test_r12_h24_nelms_reference(self) -> None:
        """Cone r=12mm, h=24mm: V = 3619.11 mm³ (Nelms et al. [14])."""
        assert cone_volume(12.0, 24.0) == pytest.approx(3619.11, abs=0.01)

    def test_is_one_third_of_cylinder(self) -> None:
        """Mathematical identity: cone = cylinder / 3 for same r, h."""
        r, h = 15.0, 30.0
        assert cone_volume(r, h) == pytest.approx(
            cylinder_volume(r, h) / 3.0, rel=1e-12
        )

    def test_r1_h1(self) -> None:
        """Unit cone: V = π/3 mm³."""
        assert cone_volume(1.0, 1.0) == pytest.approx(np.pi / 3.0, rel=1e-12)

    def test_r12_h24_in_cc(self) -> None:
        """Cone r=12mm, h=24mm: V = 3.619 cc (Nelms et al. [14])."""
        assert mm3_to_cc(cone_volume(12.0, 24.0)) == pytest.approx(3.619, abs=0.001)

    def test_rejects_zero_radius(self) -> None:
        with pytest.raises(ValueError, match="radius_mm"):
            cone_volume(0.0, 10.0)

    def test_rejects_negative_height(self) -> None:
        with pytest.raises(ValueError, match="height_mm"):
            cone_volume(5.0, -2.0)


class TestEllipsoidVolume:
    """Tests for ellipsoid_volume(semi_a, semi_b, semi_c) = (4/3)πabc."""

    def test_sphere_is_special_case(self) -> None:
        """Degenerate case: ellipsoid(r, r, r) == sphere(r)."""
        r = 10.0
        assert ellipsoid_volume(r, r, r) == pytest.approx(sphere_volume(r), rel=1e-12)

    def test_a10_b5_c3(self) -> None:
        """Ellipsoid a=10, b=5, c=3: V = (4/3)π(150) = 628.318 mm³."""
        expected = (4.0 / 3.0) * np.pi * 10.0 * 5.0 * 3.0
        assert ellipsoid_volume(10.0, 5.0, 3.0) == pytest.approx(expected, rel=1e-12)

    def test_a1_b1_c1(self) -> None:
        """Unit ellipsoid = unit sphere: V = 4π/3."""
        assert ellipsoid_volume(1.0, 1.0, 1.0) == pytest.approx(
            4.0 * np.pi / 3.0, rel=1e-12
        )

    def test_a20_b10_c5(self) -> None:
        """Ellipsoid a=20, b=10, c=5: V = (4/3)π(1000) = 4188.79 mm³."""
        expected = (4.0 / 3.0) * np.pi * 20.0 * 10.0 * 5.0
        assert ellipsoid_volume(20.0, 10.0, 5.0) == pytest.approx(expected, rel=1e-12)

    def test_rejects_zero_semi_axis(self) -> None:
        with pytest.raises(ValueError, match="semi_a_mm"):
            ellipsoid_volume(0.0, 5.0, 3.0)

    def test_rejects_negative_semi_axis(self) -> None:
        with pytest.raises(ValueError, match="semi_b_mm"):
            ellipsoid_volume(10.0, -5.0, 3.0)


class TestTorusVolume:
    """Tests for torus_volume(major_radius, minor_radius) = 2π²Rr²."""

    def test_R20_r5(self) -> None:
        """Torus R=20mm, r=5mm: V = 2π²(20)(25) = 9869.60 mm³."""
        expected = 2.0 * np.pi**2 * 20.0 * 5.0**2
        assert torus_volume(20.0, 5.0) == pytest.approx(expected, rel=1e-12)

    def test_R10_r1(self) -> None:
        """Torus R=10mm, r=1mm: V = 2π²(10)(1) = 197.39 mm³."""
        expected = 2.0 * np.pi**2 * 10.0 * 1.0**2
        assert torus_volume(10.0, 1.0) == pytest.approx(expected, rel=1e-12)

    def test_R50_r10(self) -> None:
        """Torus R=50mm, r=10mm: V = 2π²(50)(100) = 98696.04 mm³."""
        expected = 2.0 * np.pi**2 * 50.0 * 10.0**2
        assert torus_volume(50.0, 10.0) == pytest.approx(expected, rel=1e-12)

    def test_rejects_negative_major_radius(self) -> None:
        with pytest.raises(ValueError, match="major_radius_mm"):
            torus_volume(-10.0, 5.0)

    def test_rejects_zero_minor_radius(self) -> None:
        with pytest.raises(ValueError, match="minor_radius_mm"):
            torus_volume(20.0, 0.0)


class TestCylindricalShellVolume:
    """Tests for cylindrical_shell_volume = π(R² - r²)h."""

    def test_thin_shell_1mm_wall(self) -> None:
        """Shell outer=11mm, inner=10mm, h=20mm: V = π(121-100)(20)."""
        expected = np.pi * (11.0**2 - 10.0**2) * 20.0
        assert cylindrical_shell_volume(11.0, 10.0, 20.0) == pytest.approx(
            expected, rel=1e-12
        )

    def test_4mm_wall_thickness(self) -> None:
        """Shell outer=14mm, inner=10mm, h=30mm: V = π(196-100)(30)."""
        expected = np.pi * (14.0**2 - 10.0**2) * 30.0
        assert cylindrical_shell_volume(14.0, 10.0, 30.0) == pytest.approx(
            expected, rel=1e-12
        )

    def test_thick_shell(self) -> None:
        """Shell outer=20mm, inner=5mm, h=50mm: V = π(400-25)(50)."""
        expected = np.pi * (20.0**2 - 5.0**2) * 50.0
        assert cylindrical_shell_volume(20.0, 5.0, 50.0) == pytest.approx(
            expected, rel=1e-12
        )

    def test_rejects_inner_ge_outer(self) -> None:
        with pytest.raises(ValueError, match="outer_radius_mm.*inner_radius_mm"):
            cylindrical_shell_volume(10.0, 10.0, 20.0)

    def test_rejects_inner_greater_than_outer(self) -> None:
        with pytest.raises(ValueError, match="outer_radius_mm.*inner_radius_mm"):
            cylindrical_shell_volume(5.0, 10.0, 20.0)

    def test_rejects_negative_height(self) -> None:
        with pytest.raises(ValueError, match="height_mm"):
            cylindrical_shell_volume(10.0, 5.0, -1.0)


class TestRectangularParallelepipedVolume:
    """Tests for rectangular_parallelepiped_volume = lwh."""

    def test_cube_10mm(self) -> None:
        """10mm cube: V = 1000 mm³."""
        assert rectangular_parallelepiped_volume(10.0, 10.0, 10.0) == pytest.approx(
            1000.0, rel=1e-12
        )

    def test_l20_w10_h5(self) -> None:
        """Rectangular block 20×10×5: V = 1000 mm³."""
        assert rectangular_parallelepiped_volume(20.0, 10.0, 5.0) == pytest.approx(
            1000.0, rel=1e-12
        )

    def test_l1_w1_h1(self) -> None:
        """Unit cube: V = 1 mm³."""
        assert rectangular_parallelepiped_volume(1.0, 1.0, 1.0) == pytest.approx(
            1.0, rel=1e-12
        )

    def test_rejects_zero_dimension(self) -> None:
        with pytest.raises(ValueError, match="length_mm"):
            rectangular_parallelepiped_volume(0.0, 10.0, 5.0)

    def test_rejects_negative_dimension(self) -> None:
        with pytest.raises(ValueError, match="width_mm"):
            rectangular_parallelepiped_volume(10.0, -5.0, 5.0)


class TestMm3ToCc:
    """Tests for mm3_to_cc unit conversion."""

    def test_1000_mm3_is_1_cc(self) -> None:
        assert mm3_to_cc(1000.0) == pytest.approx(1.0, rel=1e-12)

    def test_sphere_r10(self) -> None:
        """4188.79 mm³ = 4.189 cc (RFC §9 Task 1.1)."""
        assert mm3_to_cc(4188.79) == pytest.approx(4.18879, rel=1e-6)

    def test_zero_volume(self) -> None:
        assert mm3_to_cc(0.0) == pytest.approx(0.0, abs=1e-15)

    def test_mm3_per_cc_constant(self) -> None:
        assert MM3_PER_CC == 1000.0
