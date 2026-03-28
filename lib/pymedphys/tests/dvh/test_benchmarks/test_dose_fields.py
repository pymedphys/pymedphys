"""Tests for analytical dose field evaluation functions.

See RFC §9 Task 1.2 for specification.
"""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._benchmarks._dose_fields import (
    linear_gradient_dose,
    radial_gaussian_dose,
)


class TestLinearGradientDose:
    """Tests for linear_gradient_dose(z_mm, d0_gy, gradient_gy_per_mm)."""

    def test_zero_gradient_is_constant(self) -> None:
        """D(z) = D₀ when g = 0."""
        z = np.array([-10.0, 0.0, 5.0, 20.0])
        result = linear_gradient_dose(z, d0_gy=50.0, gradient_gy_per_mm=0.0)
        np.testing.assert_array_equal(result, 50.0)

    def test_positive_gradient_at_origin(self) -> None:
        """D(0) = D₀."""
        result = linear_gradient_dose(0.0, d0_gy=30.0, gradient_gy_per_mm=1.5)
        assert float(result[0]) == pytest.approx(30.0, rel=1e-12)

    def test_positive_gradient_known_values(self) -> None:
        """D(z) = 50 + 2z at z = [-10, 0, 5, 10]."""
        z = np.array([-10.0, 0.0, 5.0, 10.0])
        expected = np.array([30.0, 50.0, 60.0, 70.0])
        result = linear_gradient_dose(z, d0_gy=50.0, gradient_gy_per_mm=2.0)
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_negative_gradient(self) -> None:
        """D(z) = 50 - 1z at z = [0, 10, 20]."""
        z = np.array([0.0, 10.0, 20.0])
        expected = np.array([50.0, 40.0, 30.0])
        result = linear_gradient_dose(z, d0_gy=50.0, gradient_gy_per_mm=-1.0)
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_scalar_input(self) -> None:
        """Scalar input returns 1-element array."""
        result = linear_gradient_dose(5.0, d0_gy=10.0, gradient_gy_per_mm=2.0)
        assert result.shape == (1,)
        assert float(result[0]) == pytest.approx(20.0, rel=1e-12)


class TestRadialGaussianDose:
    """Tests for radial_gaussian_dose(r_mm, amplitude_gy, sigma_mm)."""

    def test_peak_at_origin(self) -> None:
        """D(0) = A."""
        result = radial_gaussian_dose(0.0, amplitude_gy=60.0, sigma_mm=10.0)
        assert float(result[0]) == pytest.approx(60.0, rel=1e-12)

    def test_decay_at_one_sigma(self) -> None:
        """D(σ) = A·exp(-0.5) ≈ 0.6065·A."""
        result = radial_gaussian_dose(10.0, amplitude_gy=60.0, sigma_mm=10.0)
        expected = 60.0 * np.exp(-0.5)
        assert float(result[0]) == pytest.approx(expected, rel=1e-12)

    def test_decay_at_two_sigma(self) -> None:
        """D(2σ) = A·exp(-2)."""
        result = radial_gaussian_dose(20.0, amplitude_gy=60.0, sigma_mm=10.0)
        expected = 60.0 * np.exp(-2.0)
        assert float(result[0]) == pytest.approx(expected, rel=1e-12)

    def test_vectorized(self) -> None:
        """Multiple radii evaluated at once."""
        r = np.array([0.0, 10.0, 20.0])
        result = radial_gaussian_dose(r, amplitude_gy=100.0, sigma_mm=10.0)
        expected = 100.0 * np.exp(-(r**2) / (2.0 * 100.0))
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_rejects_zero_amplitude(self) -> None:
        with pytest.raises(ValueError, match="amplitude_gy"):
            radial_gaussian_dose(5.0, amplitude_gy=0.0, sigma_mm=10.0)

    def test_rejects_negative_sigma(self) -> None:
        with pytest.raises(ValueError, match="sigma_mm"):
            radial_gaussian_dose(5.0, amplitude_gy=60.0, sigma_mm=-1.0)

    def test_rejects_negative_radius(self) -> None:
        """Negative radial distance is semantically invalid."""
        with pytest.raises(ValueError, match="r_mm must be non-negative"):
            radial_gaussian_dose(-5.0, amplitude_gy=60.0, sigma_mm=10.0)

    def test_rejects_negative_in_array(self) -> None:
        """Array containing any negative r_mm is rejected."""
        with pytest.raises(ValueError, match="r_mm must be non-negative"):
            radial_gaussian_dose(
                np.array([0.0, 5.0, -1.0]), amplitude_gy=60.0, sigma_mm=10.0
            )
