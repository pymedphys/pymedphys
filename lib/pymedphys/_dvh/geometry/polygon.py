# lib/pymedphys/_dvh/geometry/polygon.py
from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(cache=True)
def _point_in_poly(y: float, x: float, poly_xy: np.ndarray) -> bool:
    """
    Ray casting even-odd test for a single point vs one polygon (no holes).
    poly_xy: (M,2) with (row, col) coordinates.
    """
    inside = False
    n = poly_xy.shape[0]
    for i in range(n):
        y0, x0 = poly_xy[i, 0], poly_xy[i, 1]
        y1, x1 = poly_xy[(i + 1) % n, 0], poly_xy[(i + 1) % n, 1]

        # edge intersects horizontal ray?
        intersects = ((x0 > x) != (x1 > x)) and (
            y < (y1 - y0) * (x - x0) / (x1 - x0 + 1e-18) + y0
        )
        if intersects:
            inside = not inside
    return inside


@njit(cache=True, parallel=True)
def rasterise_fraction(rows: int, cols: int, polys: np.ndarray, sub: int) -> np.ndarray:
    """
    Sub-voxel rasterisation with rings/holes via even-odd parity across polygons.

    Parameters
    ----------
    rows, cols : int
    polys : (P, Mmax, 2) float32
        Padded stack of polygons; a NaN row marks the sentinel/end.
    sub : int
        sub×sub uniform sub-samples per pixel in index space.

    Returns
    -------
    frac : (rows, cols) float32 in [0,1]
    """
    frac = np.zeros((rows, cols), dtype=np.float32)
    inv = 1.0 / (sub * sub)

    for i in prange(rows):
        for j in range(cols):
            inside_count = 0

            # sub-grid samples
            for si in range(sub):
                for sj in range(sub):
                    y = i + (si + 0.5) / sub  # row coordinate
                    x = j + (sj + 0.5) / sub  # col coordinate

                    # even-odd parity across all polygons (rings/holes supported)
                    inside = False
                    for p in range(polys.shape[0]):
                        poly = polys[p]
                        if np.isnan(poly[0, 0]):
                            break
                        if _point_in_poly(y, x, poly):
                            inside = not inside

                    if inside:
                        inside_count += 1

            frac[i, j] = inside_count * inv

    return frac
