# pymedphys/_dvh/inclusion.py
"""
In-slice polygon inclusion (Sprint 1).

Even–odd rule point-in-polygon with support for holes; vectorised over a
regular (Y, X) lattice. We deliberately avoid special-casing edges and rely on
the standard ray-crossing predicate. This yields stable, unbiased area/volume
on lattice-centre sampling and matches analytic areas for axis-aligned cases.
"""

from __future__ import annotations

from typing import Iterable, Literal

import numpy as np
from numpy.typing import NDArray

Rule = Literal["even_odd", "winding"]  # winding kept as API placeholder
FloatA = NDArray[np.floating]
BoolA = NDArray[np.bool_]

__all__ = ["polygon_mask"]


def _ray_crossing_mask(X: FloatA, Y: FloatA, poly_xy: FloatA) -> BoolA:
    """
    Vectorised even–odd mask via the classic ray-crossing test.

    Implementation detail
    ---------------------
    We toggle where the horizontal ray to +∞ intersects an edge for which
    ((y1 > Y) != (y2 > Y)) and X < x_intersect. This handles vertices cleanly
    and avoids double-counting.
    """
    x = poly_xy[:, 0]
    y = poly_xy[:, 1]
    n = len(poly_xy)

    inside = np.zeros_like(X, dtype=bool)

    for i in range(n):
        x1, y1 = x[i], y[i]
        x2, y2 = x[(i + 1) % n], y[(i + 1) % n]

        cond = (y1 > Y) != (y2 > Y)
        # Safe division; cond ensures denominator != 0
        xints = (x2 - x1) * (Y - y1) / (y2 - y1 + 1e-30) + x1
        inside ^= cond & (X < xints)

    return inside


def polygon_mask(
    X: FloatA,
    Y: FloatA,
    outer_xy: FloatA,
    holes: Iterable[FloatA] = (),
    rule: Rule = "even_odd",
) -> BoolA:
    """
    Rasterise a polygon-with-holes footprint on a (Y, X) lattice.

    Parameters
    ----------
    X, Y : 2D float arrays (meshgrid of world coordinates)
    outer_xy : (N, 2) float
        Outer ring vertices (x, y). Closedness not required.
    holes : iterable of (Mi, 2) float arrays
        Rings to subtract from the outer polygon.

    Returns
    -------
    2D boolean mask
    """
    if rule != "even_odd":
        raise ValueError("Only 'even_odd' is implemented at Sprint 1.")

    mask = _ray_crossing_mask(X, Y, np.asarray(outer_xy, dtype=float))
    for h in holes:
        mask &= ~_ray_crossing_mask(X, Y, np.asarray(h, dtype=float))
    return mask
