"""Tests for shared validation utilities."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._validators import (
    _validate_finite_array,
    _validate_in_range,
    _validate_nonneg_array,
    _validate_nonneg_finite,
    _validate_positive_finite,
    _validate_strictly_increasing,
)


class TestValidateFiniteArray:
    def test_accepts_finite_array(self) -> None:
        _validate_finite_array(np.array([1.0, 2.0, 3.0]), "test")

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_finite_array(np.array([1.0, float("nan"), 3.0]), "test")

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_finite_array(np.array([1.0, float("inf")]), "test")

    def test_rejects_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_finite_array(np.array([float("-inf"), 1.0]), "test")


class TestValidateInRange:
    def test_accepts_values_in_range(self) -> None:
        _validate_in_range(np.array([0.0, 0.5, 1.0]), "test", 0.0, 1.0)

    def test_rejects_below_range(self) -> None:
        with pytest.raises(ValueError, match="\\[0.0, 1.0\\]"):
            _validate_in_range(np.array([-0.1, 0.5]), "test", 0.0, 1.0)

    def test_rejects_above_range(self) -> None:
        with pytest.raises(ValueError, match="\\[0.0, 1.0\\]"):
            _validate_in_range(np.array([0.5, 1.1]), "test", 0.0, 1.0)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_in_range(np.array([float("nan")]), "test", 0.0, 1.0)


class TestValidatePositiveFinite:
    def test_accepts_positive(self) -> None:
        _validate_positive_finite(1.0, "test")

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="strictly positive"):
            _validate_positive_finite(0.0, "test")

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="strictly positive"):
            _validate_positive_finite(-1.0, "test")

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_positive_finite(float("nan"), "test")

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_positive_finite(float("inf"), "test")


class TestValidateNonnegFinite:
    def test_accepts_zero(self) -> None:
        _validate_nonneg_finite(0.0, "test")

    def test_accepts_positive(self) -> None:
        _validate_nonneg_finite(5.0, "test")

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            _validate_nonneg_finite(-0.1, "test")

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _validate_nonneg_finite(float("nan"), "test")


class TestValidateStrictlyIncreasing:
    def test_accepts_increasing(self) -> None:
        _validate_strictly_increasing(np.array([1.0, 2.0, 3.0]), "test")

    def test_rejects_equal_adjacent(self) -> None:
        with pytest.raises(ValueError, match="strictly increasing"):
            _validate_strictly_increasing(np.array([1.0, 2.0, 2.0]), "test")

    def test_rejects_decreasing(self) -> None:
        with pytest.raises(ValueError, match="strictly increasing"):
            _validate_strictly_increasing(np.array([1.0, 3.0, 2.0]), "test")

    def test_accepts_single_element(self) -> None:
        _validate_strictly_increasing(np.array([1.0]), "test")

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_strictly_increasing(np.array([1.0, float("nan"), 3.0]), "test")


class TestValidateNonnegArray:
    def test_accepts_nonneg(self) -> None:
        _validate_nonneg_array(np.array([0.0, 1.0, 2.0]), "test")

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            _validate_nonneg_array(np.array([1.0, -0.1]), "test")

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            _validate_nonneg_array(np.array([float("nan")]), "test")
