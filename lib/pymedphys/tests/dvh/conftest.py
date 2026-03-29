"""Shared fixtures for DVH module tests."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture()
def simple_affine() -> np.ndarray:
    """A 4x4 affine for a uniform 2.5mm grid at origin (-10, -20, -30)."""
    return np.array(
        [
            [0, 0, 2.5, -10.0],
            [0, 2.5, 0, -20.0],
            [2.5, 0, 0, -30.0],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )


@pytest.fixture()
def unit_square_points() -> np.ndarray:
    """A 1mm x 1mm square polygon (4 vertices, CCW)."""
    return np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float64)


@pytest.fixture()
def triangle_points() -> np.ndarray:
    """A right triangle polygon (3 vertices, CCW)."""
    return np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
