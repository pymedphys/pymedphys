"""Shared invariant-enforcement utilities for DVH domain types.

These validators are used across constructors to enforce documented
invariants at construction time. Once an object passes validation,
it is guaranteed valid for its lifetime (frozen dataclass).

All validators raise ``ValueError`` on failure.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def _validate_finite_array(
    arr: npt.NDArray[np.float64],
    name: str,
) -> None:
    """Validate that all elements of an array are finite.

    Parameters
    ----------
    arr : npt.NDArray[np.float64]
        Array to validate.
    name : str
        Name used in error messages.

    Raises
    ------
    ValueError
        If any element is NaN, +Inf, or -Inf.
    """
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values (NaN or Inf)")


def _validate_in_range(
    arr: npt.NDArray[np.float64],
    name: str,
    low: float,
    high: float,
) -> None:
    """Validate that all elements fall within [low, high].

    Parameters
    ----------
    arr : npt.NDArray[np.float64]
        Array to validate.
    name : str
        Name used in error messages.
    low : float
        Minimum allowed value (inclusive).
    high : float
        Maximum allowed value (inclusive).

    Raises
    ------
    ValueError
        If any element falls outside [low, high] or is non-finite.
    """
    _validate_finite_array(arr, name)
    if np.any(arr < low) or np.any(arr > high):
        raise ValueError(
            f"{name} values must be in [{low}, {high}], "
            f"got range [{float(np.min(arr))}, {float(np.max(arr))}]"
        )


def _validate_positive_finite(value: float, name: str) -> None:
    """Validate that a scalar is strictly positive and finite.

    Parameters
    ----------
    value : float
        Scalar to validate.
    name : str
        Name used in error messages.

    Raises
    ------
    ValueError
        If value is not finite or not strictly positive.
    """
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if value <= 0:
        raise ValueError(f"{name} must be strictly positive, got {value}")


def _validate_nonneg_finite(value: float, name: str) -> None:
    """Validate that a scalar is non-negative and finite.

    Parameters
    ----------
    value : float
        Scalar to validate.
    name : str
        Name used in error messages.

    Raises
    ------
    ValueError
        If value is not finite or negative.
    """
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def _validate_strictly_increasing(
    arr: npt.NDArray[np.float64],
    name: str,
) -> None:
    """Validate that array values are strictly increasing.

    Parameters
    ----------
    arr : npt.NDArray[np.float64]
        1D array to validate.
    name : str
        Name used in error messages.

    Raises
    ------
    ValueError
        If any adjacent pair is not strictly increasing, or if
        the array contains non-finite values.
    """
    _validate_finite_array(arr, name)
    if len(arr) < 2:
        return
    diffs = np.diff(arr)
    if np.any(diffs <= 0):
        raise ValueError(f"{name} must be strictly increasing")


def _validate_nonneg_array(
    arr: npt.NDArray[np.float64],
    name: str,
) -> None:
    """Validate that all elements are finite and non-negative.

    Parameters
    ----------
    arr : npt.NDArray[np.float64]
        Array to validate.
    name : str
        Name used in error messages.

    Raises
    ------
    ValueError
        If any element is negative or non-finite.
    """
    _validate_finite_array(arr, name)
    if np.any(arr < 0):
        raise ValueError(f"{name} contains negative values")
