# tests/dvh/unit/test_inclusion.py
"""
Inclusion with holes: area check on nested squares across lattice offsets.
"""

import numpy as np

from pymedphys._dvh.inclusion import polygon_mask


def _area_from_mask(mask, dx, dy):
    return mask.sum() * dx * dy


def test_polygon_mask_with_hole_area_matches():
    dx, dy = 1.0, 1.0
    xs = np.arange(-15.0, 15.0, dx)
    ys = np.arange(-15.0, 15.0, dy)

    X, Y = np.meshgrid(xs, ys)

    # Outer 20x20 square centred at origin, inner 10x10 hole
    outer = np.array([[-10, -10], [10, -10], [10, 10], [-10, 10]], dtype=float)
    hole = np.array([[-5, -5], [5, -5], [5, 5], [-5, 5]], dtype=float)

    m = polygon_mask(X, Y, outer, [hole], rule="even_odd")
    area_est = _area_from_mask(m, dx, dy)
    area_true = (20 * 20) - (10 * 10)

    # Within ~1 voxel area tolerance
    assert abs(area_est - area_true) <= (dx * dy)
