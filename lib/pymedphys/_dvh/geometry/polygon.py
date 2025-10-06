from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(cache=True)
def _point_in_poly(x: float, y: float, poly_xy: np.ndarray) -> bool:
    """
    Ray casting even-odd test for a single point vs one polygon (no holes).
    poly_xy: (M,2) with (row, col) coordinates.
    """
    inside = False
    n = poly_xy.shape[0]
    for i in range(n):
        x0, y0 = poly_xy[i, 0], poly_xy[i, 1]
        x1, y1 = poly_xy[(i + 1) % n, 0], poly_xy[(i + 1) % n, 1]
        intersects = ((y0 > y) != (y1 > y)) and (
            x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-18) + x0
        )
        if intersects:
            inside = not inside
    return inside


@njit(cache=True, parallel=True)
def rasterise_fraction(rows: int, cols: int, polys: np.ndarray, sub: int) -> np.ndarray:
    """
    Sub-voxel rasterisation: for each (row,col) cell, sample sub*sub sub-points
    uniformly in [i,i+1)×[j,j+1) (index space) and compute fraction inside any polygon.

    polys: concatenated list with separators; we pass as (P, Mmax, 2) where padded rows
    with NaNs delimit polygons. Simpler: require polys_list flattened beforehand.
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
                    # test against each polygon in the stack until NaN row
                    hit = False
                    for p in range(polys.shape[0]):
                        poly = polys[p]
                        if np.isnan(poly[0, 0]):
                            break
                        if _point_in_poly(y, x, poly):
                            hit = True
                            break
                    if hit:
                        inside_count += 1
            frac[i, j] = inside_count * inv
    return frac
