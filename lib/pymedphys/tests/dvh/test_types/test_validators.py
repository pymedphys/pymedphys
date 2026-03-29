"""Tests for shared validator helpers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pymedphys._dvh._types._validators import (
    validate_finite,
    validate_finite_array,
    validate_in_range,
    validate_nonneg_finite,
    validate_positive_finite,
)


class TestValidatePositiveFinite:
    def test_accepts_positive(self) -> None:
        assert validate_positive_finite("x", 1.0) == 1.0

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            validate_positive_finite("x", 0.0)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            validate_positive_finite("x", -1.0)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_positive_finite("x", float("nan"))

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_positive_finite("x", float("inf"))

    def test_rejects_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_positive_finite("x", float("-inf"))


class TestValidateNonnegFinite:
    def test_accepts_zero(self) -> None:
        assert validate_nonneg_finite("x", 0.0) == 0.0

    def test_accepts_positive(self) -> None:
        assert validate_nonneg_finite("x", 5.0) == 5.0

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            validate_nonneg_finite("x", -0.1)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_nonneg_finite("x", float("nan"))

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_nonneg_finite("x", float("inf"))


class TestValidateFinite:
    def test_accepts_normal(self) -> None:
        assert validate_finite("x", 42.0) == 42.0

    def test_accepts_negative(self) -> None:
        assert validate_finite("x", -1.0) == -1.0

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_finite("x", float("nan"))

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_finite("x", float("inf"))


class TestValidateInRange:
    def test_accepts_in_range(self) -> None:
        assert validate_in_range("x", 0.5, 0.0, 1.0) == 0.5

    def test_accepts_boundaries(self) -> None:
        assert validate_in_range("x", 0.0, 0.0, 1.0) == 0.0
        assert validate_in_range("x", 1.0, 0.0, 1.0) == 1.0

    def test_rejects_below(self) -> None:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            validate_in_range("x", -0.1, 0.0, 1.0)

    def test_rejects_above(self) -> None:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            validate_in_range("x", 1.1, 0.0, 1.0)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_in_range("x", float("nan"), 0.0, 1.0)


class TestValidateFiniteArray:
    def test_accepts_finite(self) -> None:
        arr = np.array([1.0, 2.0, 3.0])
        result = validate_finite_array("a", arr)
        assert result is arr

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            validate_finite_array("a", np.array([1.0, float("nan"), 3.0]))

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            validate_finite_array("a", np.array([float("inf"), 2.0]))

    def test_rejects_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            validate_finite_array("a", np.array([float("-inf")]))

    def test_validates_ndim(self) -> None:
        with pytest.raises(ValueError, match="2D"):
            validate_finite_array("a", np.array([1.0, 2.0]), ndim=2)

    def test_accepts_correct_ndim(self) -> None:
        arr = np.array([[1.0, 2.0]])
        validate_finite_array("a", arr, ndim=2)
