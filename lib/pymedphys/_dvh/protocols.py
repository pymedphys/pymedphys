"""Strategy protocols for the PyMedPhys DVH engine.

This module defines the computation-dispatch interfaces that allow the DVH
engine to swap algorithms without modifying the core computation code:

- ``PointInPolygonStrategy``: determines which voxels lie inside a contour.
- ``InterSliceStrategy``: interpolates contour geometry between axial slices.
- ``EndCapStrategy``: determines the z-extent of terminal contour slices.

These are structural-subtyping protocols (PEP 544).  Any callable with the
right signature satisfies the protocol — no inheritance required.  A plain
function, a lambda, or a callable class instance all work.

The MVP ships one implementation of each (winding number, right prism,
half-slab variants).  The protocols exist so that post-MVP extensions
(ray-casting, shape-based interpolation, tapered end-caps) can be added
by writing a new function and passing it to ``compute_dvh``, not by
refactoring the engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from pymedphys._dvh.types import FloatArray2D, PlanarContour

# ---------------------------------------------------------------------------
# Type aliases used only in protocol signatures
# ---------------------------------------------------------------------------

BoolArray1D = npt.NDArray[np.bool_]


# ---------------------------------------------------------------------------
# Point-in-polygon
# ---------------------------------------------------------------------------


@runtime_checkable
class PointInPolygonStrategy(Protocol):
    """Determine which query points lie inside (or on) a planar contour.

    This is the per-slice inclusion test at the heart of binary voxelisation.
    Boundary points are defined as **inside** the structure (§5.1 of the
    project plan).

    Parameters
    ----------
    query_points_xy_mm : FloatArray2D
        Shape ``(M, 2)`` array of query-point XY coordinates in mm.
    contour_xy_mm : FloatArray2D
        Shape ``(N, 2)`` array of closed-polygon XY vertices in mm.

    Returns
    -------
    BoolArray1D
        Length-``M`` boolean mask.  ``True`` means the point is inside
        or on the boundary of the contour.
    """

    def __call__(
        self,
        query_points_xy_mm: FloatArray2D,
        contour_xy_mm: FloatArray2D,
        /,
    ) -> BoolArray1D: ...


# ---------------------------------------------------------------------------
# Inter-slice interpolation
# ---------------------------------------------------------------------------


@runtime_checkable
class InterSliceStrategy(Protocol):
    """Interpolate contour geometry at a z position between two slices.

    Given two bounding contours and a target z, return a new
    ``PlanarContour`` at that z with interpolated vertex positions.

    The MVP uses right-prism interpolation (the lower contour's geometry
    is extruded unchanged between slices).  Post-MVP extensions may use
    shape-based morphing that blends upper and lower vertices.

    Parameters
    ----------
    lower_contour : PlanarContour
        The contour on the slice immediately below ``z_mm``.
    upper_contour : PlanarContour
        The contour on the slice immediately above ``z_mm``.
    z_mm : float
        The target axial position for interpolation.

    Returns
    -------
    PlanarContour
        A new contour at ``z_mm`` with interpolated vertex positions.
    """

    def __call__(
        self,
        lower_contour: PlanarContour,
        upper_contour: PlanarContour,
        z_mm: float,
        /,
    ) -> PlanarContour: ...


# ---------------------------------------------------------------------------
# End-cap
# ---------------------------------------------------------------------------


@runtime_checkable
class EndCapStrategy(Protocol):
    """Determine the z-extent owned by a terminal (end) contour.

    The returned tuple ``(z_lower_mm, z_upper_mm)`` expresses a half-open
    interval ``[z_lower, z_upper)`` consistent with the slab-ownership
    convention (§5.3 of the project plan): grid points exactly on a
    midpoint belong to the lower slab.

    The MVP provides three strategies:

    - ``half_slab``: extend by half the neighbour spacing.
    - ``capped_half_slab``: like ``half_slab`` but capped at a maximum
      extension (default 1.5 mm).
    - ``no_endcap``: no extension beyond the contour slice.

    Parameters
    ----------
    contour : PlanarContour
        The terminal (inferior or superior) contour.
    neighbour_spacing_mm : float
        The axial spacing to the nearest neighbouring contour slice.
    is_superior : bool
        ``True`` if this is the most-superior (highest-z) end contour.

    Returns
    -------
    tuple[float, float]
        ``(z_lower_mm, z_upper_mm)`` — the half-open z-extent owned by
        this end contour.
    """

    def __call__(
        self,
        contour: PlanarContour,
        neighbour_spacing_mm: float,
        is_superior: bool,
        /,
    ) -> tuple[float, float]: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "BoolArray1D",
    "EndCapStrategy",
    "InterSliceStrategy",
    "PointInPolygonStrategy",
]
