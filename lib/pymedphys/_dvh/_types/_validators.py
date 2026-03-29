"""Shared validators for the DVH type layer.

Provides helpers to reject NaN, Inf, and out-of-range values
consistently across all domain types.

All scalar validators coerce via ``float()`` for numpy scalar
compatibility, and return the validated value so callers can use
``x = validate_positive_finite('x', x)`` patterns.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt


def validate_positive_finite(name: str, value: float) -> float:
    """Validate that *value* is finite and strictly positive.

    Parameters
    ----------
    name : str
        Field name for error messages.
    value : float
        Value to check.

    Returns
    -------
    float
        The validated value.

    Raises
    ------
    ValueError
        If *value* is non-finite or <= 0.
    """
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def validate_nonneg_finite(name: str, value: float) -> float:
    """Validate that *value* is finite and non-negative.

    Parameters
    ----------
    name : str
        Field name for error messages.
    value : float
        Value to check.

    Returns
    -------
    float
        The validated value.

    Raises
    ------
    ValueError
        If *value* is non-finite or < 0.
    """
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def validate_finite(name: str, value: float) -> float:
    """Validate that *value* is finite (rejects NaN and Inf).

    Parameters
    ----------
    name : str
        Field name for error messages.
    value : float
        Value to check.

    Returns
    -------
    float
        The validated value.

    Raises
    ------
    ValueError
        If *value* is non-finite.
    """
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


def validate_in_range(name: str, value: float, lo: float, hi: float) -> float:
    """Validate that *value* is finite and in [lo, hi].

    Parameters
    ----------
    name : str
        Field name for error messages.
    value : float
        Value to check.
    lo : float
        Lower bound (inclusive).
    hi : float
        Upper bound (inclusive).

    Returns
    -------
    float
        The validated value.

    Raises
    ------
    ValueError
        If *value* is non-finite or outside [lo, hi].
    """
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < lo or value > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def validate_finite_array(
    name: str, arr: npt.NDArray[np.float64], ndim: int | None = None
) -> npt.NDArray[np.float64]:
    """Validate that all elements of *arr* are finite.

    Parameters
    ----------
    name : str
        Field name for error messages.
    arr : numpy array
        Array to check.
    ndim : int, optional
        If given, also validates the array dimensionality.

    Returns
    -------
    numpy array
        The validated array (same object).

    Raises
    ------
    ValueError
        If any element is non-finite or ndim doesn't match.
    """
    if ndim is not None and arr.ndim != ndim:
        raise ValueError(f"{name} must be {ndim}D, got {arr.ndim}D")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values (NaN or Inf)")
    return arr
