# src/dvhtools/raster.py

"""
Rasterization utilities for converting 2D contours into boolean masks.
"""

import numpy as np
import numba as nb
from typing import Tuple

from pymedphys._dvh.rtstruct_utils import is_inside_polygon


@nb.njit(cache=True)
def polygon_to_mask(
    polygon: np.ndarray,
    shape: Tuple[int, int],
    origin: Tuple[float, float],
    spacing: Tuple[float, float],
    include_edges: bool = True,
) -> np.ndarray:
    """
    Rasterize a closed 2D polygon into a boolean mask on a regular grid.

    Points whose grid‐cell centers lie strictly inside the polygon
    (is_inside_polygon == 1) will always be marked True.
    Points exactly on an edge or vertex (is_inside_polygon == 2)
    will be marked True only if include_edges=True.

    Parameters
    ----------
    polygon : ndarray[N,2]
        Vertices of the polygon in patient (x,y) coords. First == last.
    shape : (ny, nx)
        Output mask shape: rows (y) and columns (x).
    origin : (x0, y0)
        Patient‐coordinate of mask[0,0].
    spacing : (dx, dy)
        Grid spacing in x and y.
    include_edges : bool, default=False
        If True, treat boundary points (inside_code==2) as inside.

    Returns
    -------
    mask : ndarray[ny, nx] of bool
        True where the grid‐cell center is in the ROI.
    """
    ny, nx = shape
    x0, y0 = origin
    dx, dy = spacing

    mask = np.zeros((ny, nx), dtype=np.bool_)

    for j in range(ny):
        y = y0 + j * dy
        for i in range(nx):
            x = x0 + i * dx
            inside_code = is_inside_polygon(polygon, (x, y))
            if inside_code == 1 or (include_edges and inside_code == 2):
                mask[j, i] = True

    return mask
