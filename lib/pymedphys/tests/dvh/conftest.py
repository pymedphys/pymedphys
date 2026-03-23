"""Shared DVH test fixtures for the PyMedPhys MVP.

This provides every shared fixture used by the DVH test suite.  It is
intentionally self-contained: while the ``pymedphys._dvh`` package is still
under construction, local fallback dataclasses keep this module importable
and executable without the production type definitions.  Once
``_dvh.types`` exists the fallback is bypassed automatically.

Audience note
-------------
Comments and docstrings in this file are deliberately verbose.  The
intended audience is medical physicists who may be familiar with DVH
concepts but less so with pytest internals or computational-geometry
primitives.  Clarity is valued above brevity.

Callable ("factory") fixtures
-----------------------------
Several fixtures in this module return *functions* rather than concrete
values.  For example::

    @pytest.fixture
    def linear_dose_grid() -> Callable[..., DoseGrid]:
        return _make_linear_dose_grid

This is the standard pytest "factory as fixture" pattern.  It lets each
test call the factory with whatever parameters it needs::

    def test_example(linear_dose_grid):
        grid = linear_dose_grid("AP", resolution_mm=1.0)

If the fixture returned a single pre-built grid instead, every consuming
test would be forced to use the same parameters — or the fixture would
need ``@pytest.fixture(params=...)`` which runs *every* consumer with
*all* parameter combinations.  The factory pattern avoids both problems.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------------
import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

# ---------------------------------------------------------------------------
# Third-party — always available
# ---------------------------------------------------------------------------
import numpy as np
import numpy.typing as npt
import pytest

# ---------------------------------------------------------------------------
# Third-party — optional (Hypothesis is not required to collect tests)
# ---------------------------------------------------------------------------
try:
    from hypothesis import assume
    from hypothesis import strategies as st
except ModuleNotFoundError:  # pragma: no cover — depends on test environment
    assume = None  # type: ignore[assignment]
    st = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 — Type definitions (fallback for pre-MVP bootstrap)
# ═══════════════════════════════════════════════════════════════════════════
#
# Once ``pymedphys._dvh.types`` exists these imports succeed and the local
# definitions below are never reached.  The guard uses ``ImportError``
# (not a bare ``Exception``) so that genuine bugs inside a partially-written
# ``_dvh.types`` module are not silently swallowed.
# ═══════════════════════════════════════════════════════════════════════════

try:  # pragma: no cover — exercised naturally once ``_dvh.types`` exists
    from pymedphys._dvh.types import DoseGrid, PlanarContour, Structure
except ImportError:  # pragma: no cover — local fallback for the pre-MVP state

    @dataclass(frozen=True)
    class PlanarContour:  # type: ignore[no-redef]
        """A single closed planar contour on one axial slice.

        Attributes
        ----------
        z_mm
            Slice coordinate in the DICOM patient z-axis (superior +).
        points_xy_mm
            Vertex array of shape ``(N, 2)`` in DICOM patient x/y
            coordinates (patient-left +, patient-posterior +).
        geometric_type
            DICOM-style contour geometric type string.
            ``"CLOSED_PLANAR"`` is the standard default.
            ``"CLOSED_PLANAR_XOR"`` signals explicit XOR combination
            with other contours on the same slice.
        """

        z_mm: float
        points_xy_mm: npt.NDArray[np.float64]
        geometric_type: str = "CLOSED_PLANAR"

    @dataclass(frozen=True)
    class Structure:  # type: ignore[no-redef]
        """A structure (ROI) defined by a stack of planar contours.

        Attributes
        ----------
        name
            Human-readable structure name (e.g. ``"PTV"``).
        number
            Numeric ROI identifier — typically the DICOM ROI Number.
        contours
            Ordered tuple of planar contours, sorted by ascending z.
        colour_rgb
            Optional display colour as ``(R, G, B)`` in 0–255.
        combination_mode
            How to combine multiple contours on the same slice:
            ``"auto"`` (default), ``"xor"``, ``"slice_union"``,
            ``"vendor_compat_xor"``.
        coordinate_frame
            Always ``"DICOM_PATIENT"`` for the MVP.
        """

        name: str
        number: int
        contours: tuple[PlanarContour, ...]
        colour_rgb: tuple[int, int, int] | None = None
        combination_mode: str = "auto"
        coordinate_frame: str = "DICOM_PATIENT"

    @dataclass(frozen=True)
    class DoseGrid:  # type: ignore[no-redef]
        """A 3-D rectilinear dose distribution.

        Attributes
        ----------
        axes_mm
            Tuple of three 1-D arrays ``(x_mm, y_mm, z_mm)`` giving the
            coordinate of every grid point along each DICOM patient axis.
        values_gy
            3-D array of dose values in Gray.  Shape is
            ``(len(x_mm), len(y_mm), len(z_mm))`` and the indexing
            contract is ``values_gy[ix, iy, iz]`` ↔
            ``(x_mm[ix], y_mm[iy], z_mm[iz])``.
        """

        axes_mm: tuple[
            npt.NDArray[np.float64],
            npt.NDArray[np.float64],
            npt.NDArray[np.float64],
        ]
        values_gy: npt.NDArray[np.float64]


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 — Synthetic test-case container
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SyntheticDVHCase:
    """Convenience container for small end-to-end synthetic test cases.

    Bundles a structure, a dose grid, and the analytically expected
    surface-dose extremes so that test functions can unpack a single
    object rather than juggling many local variables.
    """

    structure: Structure
    dose_grid: DoseGrid
    direction: str
    gradient_gy_per_mm: float
    expected_surface_min_dose_gy: float
    expected_surface_max_dose_gy: float
    notes: str


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 — Type aliases
# ═══════════════════════════════════════════════════════════════════════════

# A 2-D array of shape (N, 2) representing an ordered sequence of polygon
# vertices in the x–y plane, measured in millimetres.
PointArray = npt.NDArray[np.float64]

# A 1-D array of shape (2,) representing a single point in x–y.
# Distinguished from PointArray for clarity in computational-geometry
# helpers that operate on individual vertices.
Point2D = npt.NDArray[np.float64]


# ═══════════════════════════════════════════════════════════════════════════
# Section 4 — Module-level constants
# ═══════════════════════════════════════════════════════════════════════════

# Dimensions of the five Nelms et al. (2015) synthetic structures.
# Sphere: radius 12 mm.
# Axial cylinder: radius 12 mm, height 24 mm, long axis along z (SI).
# Rotated cylinder: radius 12 mm, height 24 mm, long axis along y (AP).
# Axial cone: base radius 12 mm, height 24 mm, apex at z = −12, base at z = +12.
# Rotated cone: base radius 12 mm, height 24 mm, apex along y.
NELMS_RADIUS_MM: float = 12.0
NELMS_HEIGHT_MM: float = 24.0
NELMS_HALF_HEIGHT_MM: float = NELMS_HEIGHT_MM / 2.0

# When a contour slice passes through the very tip of a cone or the pole
# of a sphere, the true cross-section degenerates to a point.  A single
# point is not a valid polygon, so we replace it with a tiny regular
# polygon of this radius.  At 1 µm the contributed area/volume is
# negligible relative to DVH uncertainties.
TINY_POLYGON_RADIUS_MM: float = 1.0e-3

# Number of vertices used when discretising circular cross-sections.
# 128 sides gives a polygon whose inscribed-area error relative to a true
# circle is ~0.006 %, negligible for DVH work.
DEFAULT_POLYGON_SIDES: int = 128

# Vertex count for the tiny replacement polygons at degenerate tips.
DEFAULT_TINY_POLYGON_SIDES: int = 16

# Number of y-profile sample points used when tracing the non-trivial
# cross-section of a rotated cone sliced at constant z.
DEFAULT_ROTATED_CONE_PROFILE_POINTS: int = 64


# ═══════════════════════════════════════════════════════════════════════════
# Section 5 — Low-level geometry primitives
# ═══════════════════════════════════════════════════════════════════════════


def _as_float64_points(points_xy_mm: Sequence[Sequence[float]]) -> PointArray:
    """Convert a list of ``(x, y)`` pairs to a ``float64`` vertex array.

    Raises
    ------
    ValueError
        If the resulting array is not of shape ``(N, 2)``.
    """
    points = np.asarray(points_xy_mm, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("Expected an array of shape (n_points, 2).")
    return points


def _regular_polygon(
    radius_mm: float,
    n_points: int,
    *,
    centre_xy_mm: tuple[float, float] = (0.0, 0.0),
    angle_offset_rad: float = 0.0,
) -> PointArray:
    """Generate the vertices of a regular polygon inscribed in a circle.

    Vertices are placed at equal angular intervals starting from
    ``angle_offset_rad`` and proceeding counter-clockwise.  The polygon
    is centred at ``centre_xy_mm`` with circumradius ``radius_mm``.

    All returned polygons have **counter-clockwise winding** (positive
    signed area under the shoelace formula).  This is important because
    the winding-number point-in-polygon algorithm's boundary-inclusion
    behaviour depends on consistent winding direction.
    """
    if n_points < 3:
        raise ValueError("A polygon needs at least three points.")

    angles_rad = np.linspace(0.0, math.tau, num=n_points, endpoint=False)
    angles_rad = angles_rad + angle_offset_rad

    centre_x_mm, centre_y_mm = centre_xy_mm
    x_mm = centre_x_mm + radius_mm * np.cos(angles_rad)
    y_mm = centre_y_mm + radius_mm * np.sin(angles_rad)

    return np.column_stack((x_mm, y_mm)).astype(np.float64, copy=False)


def _tiny_polygon(
    *,
    centre_xy_mm: tuple[float, float] = (0.0, 0.0),
    radius_mm: float = TINY_POLYGON_RADIUS_MM,
    n_points: int = DEFAULT_TINY_POLYGON_SIDES,
) -> PointArray:
    """Return a very small regular polygon (default ~1 µm circumradius).

    Used as a replacement for degenerate single-point cross-sections at
    cone tips and sphere poles.  The slight angular offset rotates the
    polygon so that a flat edge faces upward rather than a vertex — purely
    aesthetic and has no effect on the physics.
    """
    return _regular_polygon(
        radius_mm,
        n_points,
        centre_xy_mm=centre_xy_mm,
        angle_offset_rad=math.pi / n_points,
    )


def _rectangle_polygon(
    x_half_width_mm: float,
    y_half_width_mm: float,
    *,
    centre_xy_mm: tuple[float, float] = (0.0, 0.0),
) -> PointArray:
    """Return four vertices of an axis-aligned rectangle.

    Vertices are ordered counter-clockwise starting from the
    bottom-left corner.
    """
    cx, cy = centre_xy_mm
    return _as_float64_points(
        [
            (cx - x_half_width_mm, cy - y_half_width_mm),
            (cx + x_half_width_mm, cy - y_half_width_mm),
            (cx + x_half_width_mm, cy + y_half_width_mm),
            (cx - x_half_width_mm, cy + y_half_width_mm),
        ]
    )


def _translate_polygon(
    points_xy_mm: PointArray,
    *,
    dx_mm: float = 0.0,
    dy_mm: float = 0.0,
) -> PointArray:
    """Translate every vertex of a polygon by ``(dx_mm, dy_mm)``."""
    translation_mm = np.asarray([dx_mm, dy_mm], dtype=np.float64)
    return np.asarray(points_xy_mm, dtype=np.float64) + translation_mm


# ═══════════════════════════════════════════════════════════════════════════
# Section 6 — Axial slice-position generator
# ═══════════════════════════════════════════════════════════════════════════


def _slice_positions_with_end_slices(
    half_extent_mm: float,
    spacing_mm: float,
) -> npt.NDArray[np.float64]:
    """Generate axial slice z-positions guaranteed to include both endpoints.

    Positions run from ``-half_extent_mm`` to ``+half_extent_mm`` spaced
    by ``spacing_mm``.  If the positive endpoint does not coincide with a
    regular step it is appended as an extra position, ensuring the first
    and last contour slices always sit exactly on the geometric boundary
    of the shape.

    **Numerical note:** integer-scaled multiplication (``k * spacing_mm``)
    is used instead of repeated addition (``current += spacing_mm``).  A
    single floating-point multiplication incurs at most one ULP of
    rounding error regardless of *k*, whereas *N* successive additions
    can accumulate *O(N)* ULPs of drift.
    """
    if spacing_mm <= 0.0:
        raise ValueError("spacing_mm must be positive.")

    full_extent_mm = 2.0 * half_extent_mm
    n_steps = int(math.floor(full_extent_mm / spacing_mm + 1.0e-9))

    step_indices = np.arange(n_steps + 1, dtype=np.float64)
    positions_mm = -half_extent_mm + step_indices * spacing_mm

    # Force the first element to the exact negative endpoint.
    positions_mm[0] = -half_extent_mm

    # Ensure the positive endpoint is present and exactly valued.
    if math.isclose(float(positions_mm[-1]), half_extent_mm, abs_tol=1.0e-9):
        positions_mm[-1] = half_extent_mm
    else:
        positions_mm = np.append(positions_mm, half_extent_mm)

    return positions_mm


# ═══════════════════════════════════════════════════════════════════════════
# Section 7 — Contour and structure wrapper constructors
# ═══════════════════════════════════════════════════════════════════════════


def _planar_contour(
    z_mm: float,
    points_xy_mm: PointArray,
    *,
    geometric_type: str = "CLOSED_PLANAR",
) -> PlanarContour:
    """Construct a ``PlanarContour`` with guaranteed ``float64`` vertices."""
    return PlanarContour(
        z_mm=float(z_mm),
        points_xy_mm=np.asarray(points_xy_mm, dtype=np.float64),
        geometric_type=geometric_type,
    )


def _structure(
    name: str,
    contours: Iterable[PlanarContour],
    *,
    number: int = 1,
    colour_rgb: tuple[int, int, int] | None = None,
    combination_mode: str = "auto",
) -> Structure:
    """Construct a ``Structure`` from unsorted contours.

    Contours are sorted by ascending ``z_mm`` and the coordinate frame
    is hard-coded to ``"DICOM_PATIENT"`` (the only frame the MVP
    supports).
    """
    sorted_contours = tuple(sorted(contours, key=lambda c: c.z_mm))
    return Structure(
        name=name,
        number=number,
        contours=sorted_contours,
        colour_rgb=colour_rgb,
        combination_mode=combination_mode,
        coordinate_frame="DICOM_PATIENT",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 8 — Dose-grid builders
# ═══════════════════════════════════════════════════════════════════════════


def _symmetric_axis_mm(
    grid_extent_mm: float,
    resolution_mm: float,
) -> npt.NDArray[np.float64]:
    """Build a 1-D dose-grid axis centred on zero.

    The axis spans ``[-grid_extent_mm, +grid_extent_mm]`` with spacing
    ``resolution_mm``.  The number of points on each side is determined
    by ``round(grid_extent_mm / resolution_mm)`` so that the axis is
    always symmetric and always includes the origin.
    """
    if resolution_mm <= 0.0:
        raise ValueError("resolution_mm must be positive.")
    if grid_extent_mm <= 0.0:
        raise ValueError("grid_extent_mm must be positive.")

    n_steps_each_side = int(round(grid_extent_mm / resolution_mm))
    axis_mm = (
        np.arange(-n_steps_each_side, n_steps_each_side + 1, dtype=np.float64)
        * resolution_mm
    )

    if axis_mm.size == 0:
        raise ValueError("Dose grid axis cannot be empty.")

    return axis_mm


def _make_linear_dose_grid(
    direction: str,
    resolution_mm: float,
    grid_extent_mm: float = 30.0,
    *,
    centre_dose_gy: float = 17.0,
    gradient_gy_per_mm: float = 1.0,
) -> DoseGrid:
    """Build a 3-D dose grid with a linear gradient in one direction.

    Parameters
    ----------
    direction
        Physical direction of the gradient.  ``"AP"`` produces a
        gradient along the DICOM patient y-axis (anterior → posterior).
        ``"SI"`` produces a gradient along the patient z-axis
        (superior → inferior).  Raw axis letters are not accepted —
        this is a deliberate project convention to avoid DICOM/IEC
        coordinate confusion.
    resolution_mm
        Spacing between grid points on every axis.
    grid_extent_mm
        Half-width of the grid.  The grid spans
        ``[-grid_extent_mm, +grid_extent_mm]`` on all three axes.
    centre_dose_gy
        Dose at the grid origin.  Default is 17 Gy (per Nelms).
    gradient_gy_per_mm
        Rate of dose change per mm in the chosen direction.

    Coordinate convention
    ---------------------
    ``values_gy[ix, iy, iz]`` corresponds to the grid point
    ``(x_mm[ix], y_mm[iy], z_mm[iz])`` in DICOM patient coordinates.

    For ``direction="AP"``::

        D(x, y, z) = centre_dose_gy + gradient_gy_per_mm × y

    For ``direction="SI"``::

        D(x, y, z) = centre_dose_gy + gradient_gy_per_mm × z

    .. warning::

        The grid **will contain negative dose values** when the product
        ``gradient_gy_per_mm × grid_extent_mm`` exceeds
        ``centre_dose_gy``.  With the defaults (17 Gy centre, 1 Gy/mm
        gradient, ±30 mm extent) doses range from −13 Gy to +47 Gy.
        Negative doses are unphysical but are intentionally preserved
        because the Nelms analytical DVH formulae assume an unbounded
        linear field.  All five standard Nelms structures fit within
        ±12 mm of the origin where doses remain safely positive
        (5–29 Gy).  If a test needs strictly non-negative dose, use
        a smaller ``grid_extent_mm`` or a larger ``centre_dose_gy``.
    """
    if direction not in {"AP", "SI"}:
        raise ValueError("direction must be 'AP' or 'SI'.")

    x_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)
    y_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)
    z_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)

    values_gy = np.full(
        (x_mm.size, y_mm.size, z_mm.size), centre_dose_gy, dtype=np.float64
    )

    if direction == "AP":
        # Gradient along patient-y (axis index 1).
        values_gy = values_gy + gradient_gy_per_mm * y_mm[np.newaxis, :, np.newaxis]
    else:
        # Gradient along patient-z (axis index 2).
        values_gy = values_gy + gradient_gy_per_mm * z_mm[np.newaxis, np.newaxis, :]

    return DoseGrid(axes_mm=(x_mm, y_mm, z_mm), values_gy=values_gy)


def _make_uniform_dose_grid(
    dose_gy: float = 2.0,
    resolution_mm: float = 1.0,
    grid_extent_mm: float = 30.0,
) -> DoseGrid:
    """Build a 3-D dose grid filled with a single uniform dose value.

    Useful for testing volume-only calculations where the dose
    distribution is irrelevant.
    """
    x_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)
    y_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)
    z_mm = _symmetric_axis_mm(grid_extent_mm, resolution_mm)

    values_gy = np.full((x_mm.size, y_mm.size, z_mm.size), dose_gy, dtype=np.float64)
    return DoseGrid(axes_mm=(x_mm, y_mm, z_mm), values_gy=values_gy)


# ═══════════════════════════════════════════════════════════════════════════
# Section 9 — Circle polygon builder
# ═══════════════════════════════════════════════════════════════════════════


def _make_circle_polygon(
    radius_mm: float = NELMS_RADIUS_MM,
    n_points: int = DEFAULT_POLYGON_SIDES,
) -> PointArray:
    """Return vertices of a regular polygon approximating a circle.

    Raises ``ValueError`` for non-positive radius.
    """
    if radius_mm <= 0.0:
        raise ValueError("radius_mm must be positive.")
    return _regular_polygon(radius_mm, n_points)


# ═══════════════════════════════════════════════════════════════════════════
# Section 10 — Nelms analytical-truth geometry builders
#
# These functions construct the five synthetic shapes described in
# Nelms et al. (2015) "Methods, software and datasets to verify DVH
# calculations against analytical values".  Each shape is centred at
# the origin and defined in DICOM patient coordinates.
#
# All circular cross-sections use DEFAULT_POLYGON_SIDES (128) vertices.
# Degenerate tip/pole slices are replaced with tiny polygons rather than
# single points, satisfying the project requirement:
#   "The first and last sphere/cone slices must be tiny polygons,
#    not degenerate points."
# ═══════════════════════════════════════════════════════════════════════════


def _make_nelms_sphere_contours(
    spacing_mm: float,
) -> tuple[PlanarContour, ...]:
    """Sphere of radius 12 mm centred at the origin.

    At each axial slice z, the circular cross-section has radius
    ``r(z) = sqrt(R² − z²)``.  Slices at the poles (where r → 0)
    receive a tiny polygon instead of a degenerate point.
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_RADIUS_MM, spacing_mm)
    contours: list[PlanarContour] = []

    for z_mm in z_positions_mm:
        radial_term_mm2 = max(NELMS_RADIUS_MM**2 - float(z_mm) ** 2, 0.0)
        cross_section_radius_mm = math.sqrt(radial_term_mm2)

        if cross_section_radius_mm <= TINY_POLYGON_RADIUS_MM:
            points_xy_mm = _tiny_polygon()
        else:
            points_xy_mm = _make_circle_polygon(
                radius_mm=cross_section_radius_mm,
                n_points=DEFAULT_POLYGON_SIDES,
            )
        contours.append(_planar_contour(z_mm, points_xy_mm))

    return tuple(contours)


def _make_nelms_axial_cylinder_contours(
    spacing_mm: float,
) -> tuple[PlanarContour, ...]:
    """Cylinder of radius 12 mm, height 24 mm, long axis along z (SI).

    Every axial slice through this cylinder is an identical circle of
    radius 12 mm.  The z-extent runs from −12 mm to +12 mm.
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_HALF_HEIGHT_MM, spacing_mm)
    circle_xy_mm = _make_circle_polygon(
        radius_mm=NELMS_RADIUS_MM, n_points=DEFAULT_POLYGON_SIDES
    )
    return tuple(_planar_contour(z_mm, circle_xy_mm) for z_mm in z_positions_mm)


def _make_nelms_rotated_cylinder_contours(
    spacing_mm: float,
) -> tuple[PlanarContour, ...]:
    """Cylinder of radius 12 mm, height 24 mm, long axis along y (AP).

    When a cylinder whose circular cross-section faces along the y-axis
    is sliced at constant z, the intersection is a **rectangle**.  The
    rectangle's y-extent is always the full cylinder height (±12 mm)
    because slicing at constant z does not clip the y-direction.  Only
    the x-extent varies: ``x_half = sqrt(R² − z²)``, shrinking to zero
    at ``z = ±R``.

    Boundary slices (where x_half → 0) get a tiny but non-degenerate
    x-extent to remain valid rectangles, satisfying the project
    requirement: "Rotated cylinder cross-sections must really be
    rectangles."

    The z-extent of the slice stack is ``±NELMS_RADIUS_MM`` (not
    ``±NELMS_HALF_HEIGHT_MM``), because the cylinder's circular
    cross-section determines how far it extends in z.
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_RADIUS_MM, spacing_mm)
    contours: list[PlanarContour] = []

    for z_mm in z_positions_mm:
        x_half_width_mm = math.sqrt(max(NELMS_RADIUS_MM**2 - float(z_mm) ** 2, 0.0))
        # Clamp to a tiny but non-zero width so boundary slices remain
        # true rectangles rather than collapsing to line segments.
        x_half_width_mm = max(x_half_width_mm, TINY_POLYGON_RADIUS_MM)

        # The y-extent is constant (the full cylinder height) because
        # slicing a y-axis cylinder at constant z only narrows the
        # x-direction — the y-direction is unaffected.
        rectangle_xy_mm = _rectangle_polygon(x_half_width_mm, NELMS_HALF_HEIGHT_MM)
        contours.append(_planar_contour(z_mm, rectangle_xy_mm))

    return tuple(contours)


def _make_nelms_axial_cone_contours(
    spacing_mm: float,
) -> tuple[PlanarContour, ...]:
    """Cone with base radius 12 mm, height 24 mm, apex at z = −12 mm.

    The long axis is along z (SI).  At each slice the circular
    cross-section has radius ``r(z) = R × (z − z_tip) / H`` which
    linearly increases from 0 at the apex to R at the base.  Slices
    near the apex where r ≈ 0 receive a tiny polygon.
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_HALF_HEIGHT_MM, spacing_mm)
    tip_z_mm = -NELMS_HALF_HEIGHT_MM
    contours: list[PlanarContour] = []

    for z_mm in z_positions_mm:
        cross_section_radius_mm = (
            NELMS_RADIUS_MM * (float(z_mm) - tip_z_mm) / NELMS_HEIGHT_MM
        )
        if cross_section_radius_mm <= TINY_POLYGON_RADIUS_MM:
            points_xy_mm = _tiny_polygon()
        else:
            points_xy_mm = _make_circle_polygon(
                radius_mm=cross_section_radius_mm,
                n_points=DEFAULT_POLYGON_SIDES,
            )
        contours.append(_planar_contour(z_mm, points_xy_mm))

    return tuple(contours)


def _make_rotated_cone_slice_polygon(
    z_mm: float,
    n_profile_points: int = DEFAULT_ROTATED_CONE_PROFILE_POINTS,
) -> PointArray:
    """Compute the cross-section of a y-axis cone sliced at constant z.

    This is the most geometrically complex shape in the Nelms set.  A
    cone whose apex is at y = −H/2 and whose base circle (radius R) is
    at y = +H/2, rotated so its long axis lies along y (AP), produces
    non-circular cross-sections when sliced axially.

    The boundary is traced by sweeping y from the lowest intersection
    point to the base, computing the x half-width at each y, and
    joining the right profile to the reversed left profile.
    """
    abs_z_mm = abs(float(z_mm))

    if abs_z_mm >= NELMS_RADIUS_MM - 1.0e-12:
        # Boundary axial slices intersect the rotated cone in a single
        # point on the base rim — use a tiny polygon.
        return _tiny_polygon(centre_xy_mm=(0.0, NELMS_HALF_HEIGHT_MM))

    # Lowest y where the cone surface reaches this |z|.
    y_min_mm = (NELMS_HEIGHT_MM * abs_z_mm / NELMS_RADIUS_MM) - NELMS_HALF_HEIGHT_MM
    y_max_mm = NELMS_HALF_HEIGHT_MM

    y_mm = np.linspace(y_min_mm, y_max_mm, num=n_profile_points, dtype=np.float64)

    # At each y, the cone has local radius r(y) = R × (y + H/2) / H.
    # The x half-width at this z is sqrt(r(y)² − z²).
    radial_term_mm = NELMS_RADIUS_MM * (y_mm + NELMS_HALF_HEIGHT_MM) / NELMS_HEIGHT_MM
    x_half_width_mm = np.sqrt(
        np.clip(radial_term_mm**2 - abs_z_mm**2, a_min=0.0, a_max=None)
    )

    if float(np.max(x_half_width_mm)) <= TINY_POLYGON_RADIUS_MM:
        return _tiny_polygon(centre_xy_mm=(0.0, y_max_mm))

    # Trace the right profile (positive x) then the left profile
    # (negative x, reversed) to form a closed polygon.
    right_side_xy_mm = np.column_stack((x_half_width_mm, y_mm))
    left_side_xy_mm = np.column_stack((-x_half_width_mm[::-1], y_mm[::-1]))

    # Drop the last point of the left side to avoid duplicating the
    # apex vertex where both profiles meet.
    points_xy_mm = np.vstack((right_side_xy_mm, left_side_xy_mm[:-1]))
    return points_xy_mm.astype(np.float64, copy=False)


def _make_nelms_rotated_cone_contours(
    spacing_mm: float,
) -> tuple[PlanarContour, ...]:
    """Cone of base radius 12 mm, height 24 mm, long axis along y (AP).

    Each axial slice produces a non-circular cross-section computed by
    ``_make_rotated_cone_slice_polygon``.  The z-extent is
    ``±NELMS_RADIUS_MM`` (determined by the base circle radius, not the
    cone height).
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_RADIUS_MM, spacing_mm)
    return tuple(
        _planar_contour(z_mm, _make_rotated_cone_slice_polygon(z_mm))
        for z_mm in z_positions_mm
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 11 — Structure with hole (annular cylinder)
# ═══════════════════════════════════════════════════════════════════════════


def _make_structure_with_hole(spacing_mm: float = 1.0) -> Structure:
    """Annular cylinder: outer radius 12 mm, inner radius 5 mm, height 24 mm.

    Each slice contains *two* contours — an outer circle and an inner
    circle — both tagged with ``CLOSED_PLANAR_XOR`` geometric type.
    The structure's ``combination_mode`` is ``"xor"`` so that the inner
    region is subtracted from the outer.

    Every slice has the same outer and inner radii (this is a right
    cylinder, not a sphere with a hole).  End-cap behaviour for this
    annular geometry is therefore driven entirely by the DVH engine's
    end-cap strategy, making it a targeted test for that code path.
    """
    z_positions_mm = _slice_positions_with_end_slices(NELMS_HALF_HEIGHT_MM, spacing_mm)
    contours: list[PlanarContour] = []

    for z_mm in z_positions_mm:
        outer_xy_mm = _make_circle_polygon(
            radius_mm=12.0, n_points=DEFAULT_POLYGON_SIDES
        )
        inner_xy_mm = _make_circle_polygon(
            radius_mm=5.0, n_points=DEFAULT_POLYGON_SIDES
        )
        contours.append(
            _planar_contour(z_mm, outer_xy_mm, geometric_type="CLOSED_PLANAR_XOR")
        )
        contours.append(
            _planar_contour(z_mm, inner_xy_mm, geometric_type="CLOSED_PLANAR_XOR")
        )

    return _structure(
        "structure_with_hole",
        contours,
        number=100,
        combination_mode="xor",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 12 — Tiny sphere and steep-gradient test case
# ═══════════════════════════════════════════════════════════════════════════


def _make_tiny_sphere_contours(
    radius_mm: float = 2.0,
    spacing_mm: float = 1.0,
) -> tuple[PlanarContour, ...]:
    """Small sphere of configurable radius, centred at the origin.

    Mechanically identical to the Nelms sphere builder but with a
    parameterised radius for use in small-volume and high-gradient
    test scenarios.
    """
    z_positions_mm = _slice_positions_with_end_slices(radius_mm, spacing_mm)
    contours: list[PlanarContour] = []

    for z_mm in z_positions_mm:
        radial_term_mm2 = max(radius_mm**2 - float(z_mm) ** 2, 0.0)
        cross_section_radius_mm = math.sqrt(radial_term_mm2)

        if cross_section_radius_mm <= TINY_POLYGON_RADIUS_MM:
            points_xy_mm = _tiny_polygon()
        else:
            points_xy_mm = _make_circle_polygon(
                radius_mm=cross_section_radius_mm,
                n_points=DEFAULT_POLYGON_SIDES,
            )
        contours.append(_planar_contour(z_mm, points_xy_mm))

    return tuple(contours)


def _make_steep_surface_gradient_case(
    contour_spacing_mm: float = 0.5,
) -> SyntheticDVHCase:
    """A small sphere in a steep dose gradient — stresses Dmin/Dmax.

    Parameters
    ----------
    contour_spacing_mm
        Axial spacing between contour slices through the sphere.
        Configurable to allow Pepin-style precision sweeps on this case.
        Default 0.5 mm gives ~9 slices through the 4 mm diameter sphere.

    Construction
    ------------
    A 2 mm radius sphere is centred at y = 1.5 mm (offset from the
    origin in the anterior–posterior direction).  It is evaluated in a
    5 Gy/mm AP gradient centred at 17 Gy.  The sphere surface spans
    y ∈ [−0.5, 3.5] mm, so the analytically expected surface doses are:

    - Surface min: 17 + 5 × (1.5 − 2.0) = **14.5 Gy**  (at y = −0.5)
    - Surface max: 17 + 5 × (1.5 + 2.0) = **34.5 Gy**  (at y = +3.5)

    The dose grid uses 0.25 mm resolution over ±10 mm (81³ ≈ 531 k
    voxels), fine enough to resolve the gradient across the structure
    but still fast in tests.
    """
    sphere_centre_y_mm = 1.5
    sphere_radius_mm = 2.0
    gradient_gy_per_mm = 5.0
    direction = "AP"

    contours = tuple(
        _planar_contour(
            contour.z_mm,
            _translate_polygon(contour.points_xy_mm, dy_mm=sphere_centre_y_mm),
            geometric_type=contour.geometric_type,
        )
        for contour in _make_tiny_sphere_contours(
            radius_mm=sphere_radius_mm, spacing_mm=contour_spacing_mm
        )
    )
    structure = _structure("steep_surface_gradient_sphere", contours, number=200)
    dose_grid = _make_linear_dose_grid(
        direction=direction,
        resolution_mm=0.25,
        grid_extent_mm=10.0,
        centre_dose_gy=17.0,
        gradient_gy_per_mm=gradient_gy_per_mm,
    )

    expected_surface_min_dose_gy = 17.0 + gradient_gy_per_mm * (
        sphere_centre_y_mm - sphere_radius_mm
    )
    expected_surface_max_dose_gy = 17.0 + gradient_gy_per_mm * (
        sphere_centre_y_mm + sphere_radius_mm
    )

    return SyntheticDVHCase(
        structure=structure,
        dose_grid=dose_grid,
        direction=direction,
        gradient_gy_per_mm=gradient_gy_per_mm,
        expected_surface_min_dose_gy=expected_surface_min_dose_gy,
        expected_surface_max_dose_gy=expected_surface_max_dose_gy,
        notes=(
            "Small axial sphere offset in patient-y and evaluated in a "
            "5 Gy/mm AP gradient to stress near-surface Dmin/Dmax "
            "behaviour."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 13 — Computational-geometry helpers (for Hypothesis strategies)
#
# These functions are used only by the Hypothesis property-based
# strategies to validate that randomly generated polygons are simple
# (non-self-intersecting) and to distinguish convex from concave
# polygons.  They are not used by the deterministic fixtures above.
# ═══════════════════════════════════════════════════════════════════════════


def _polygon_area_signed(points_xy_mm: PointArray) -> float:
    """Signed area of a polygon via the shoelace formula.

    Returns a **positive** value for counter-clockwise winding and
    **negative** for clockwise.  Used both in Hypothesis strategies
    and in the module-level self-consistency checks.
    """
    x_mm = points_xy_mm[:, 0]
    y_mm = points_xy_mm[:, 1]
    return 0.5 * float(np.sum(x_mm * np.roll(y_mm, -1) - y_mm * np.roll(x_mm, -1)))


def _segment_orientation(
    a_xy: Point2D,
    b_xy: Point2D,
    c_xy: Point2D,
) -> float:
    """Signed orientation of the triangle (a → b → c).

    Positive means counter-clockwise, negative means clockwise, zero
    means collinear.
    """
    ab_xy = b_xy - a_xy
    ac_xy = c_xy - a_xy
    return float(ab_xy[0] * ac_xy[1] - ab_xy[1] * ac_xy[0])


def _on_segment(
    a_xy: Point2D,
    b_xy: Point2D,
    c_xy: Point2D,
    tol: float = 1.0e-9,
) -> bool:
    """Check whether point *b* lies on segment *a*–*c* (collinear case)."""
    return (
        min(a_xy[0], c_xy[0]) - tol <= b_xy[0] <= max(a_xy[0], c_xy[0]) + tol
        and min(a_xy[1], c_xy[1]) - tol <= b_xy[1] <= max(a_xy[1], c_xy[1]) + tol
    )


def _segments_intersect(
    p1_xy: Point2D,
    p2_xy: Point2D,
    q1_xy: Point2D,
    q2_xy: Point2D,
    *,
    tol: float = 1.0e-9,
) -> bool:
    """Return ``True`` if line segments (p1–p2) and (q1–q2) intersect."""
    o1 = _segment_orientation(p1_xy, p2_xy, q1_xy)
    o2 = _segment_orientation(p1_xy, p2_xy, q2_xy)
    o3 = _segment_orientation(q1_xy, q2_xy, p1_xy)
    o4 = _segment_orientation(q1_xy, q2_xy, p2_xy)

    # General case: segments straddle each other.
    if (o1 > tol and o2 < -tol or o1 < -tol and o2 > tol) and (
        o3 > tol and o4 < -tol or o3 < -tol and o4 > tol
    ):
        return True

    # Degenerate / collinear overlap cases.
    if abs(o1) <= tol and _on_segment(p1_xy, q1_xy, p2_xy, tol):
        return True
    if abs(o2) <= tol and _on_segment(p1_xy, q2_xy, p2_xy, tol):
        return True
    if abs(o3) <= tol and _on_segment(q1_xy, p1_xy, q2_xy, tol):
        return True
    if abs(o4) <= tol and _on_segment(q1_xy, p2_xy, q2_xy, tol):
        return True

    return False


def _is_simple_polygon(points_xy_mm: PointArray) -> bool:
    """Check that no non-adjacent edges of the polygon intersect.

    Also requires a non-negligible area (> 10⁻⁶ mm²) to exclude
    degenerate near-zero-area configurations.
    """
    n_points = len(points_xy_mm)
    if n_points < 3:
        return False

    for index_a in range(n_points):
        a1_xy = points_xy_mm[index_a]
        a2_xy = points_xy_mm[(index_a + 1) % n_points]

        for index_b in range(index_a + 1, n_points):
            # Skip edges that share a vertex with edge a.
            if index_b in {index_a, (index_a + 1) % n_points}:
                continue
            if (index_b + 1) % n_points == index_a:
                continue

            b1_xy = points_xy_mm[index_b]
            b2_xy = points_xy_mm[(index_b + 1) % n_points]
            if _segments_intersect(a1_xy, a2_xy, b1_xy, b2_xy):
                return False

    return abs(_polygon_area_signed(points_xy_mm)) > 1.0e-6


def _is_concave_polygon(points_xy_mm: PointArray) -> bool:
    """Return ``True`` if the polygon has at least one reflex angle.

    A polygon with fewer than 4 vertices is always convex (or
    degenerate), so this returns ``False`` for triangles.
    """
    n_points = len(points_xy_mm)
    if n_points < 4:
        return False

    signs: list[int] = []
    for index in range(n_points):
        a_xy = points_xy_mm[index]
        b_xy = points_xy_mm[(index + 1) % n_points]
        c_xy = points_xy_mm[(index + 2) % n_points]
        cross_product = _segment_orientation(a_xy, b_xy, c_xy)
        if abs(cross_product) <= 1.0e-9:
            continue
        signs.append(1 if cross_product > 0.0 else -1)

    return bool(signs) and min(signs) != max(signs)


# ═══════════════════════════════════════════════════════════════════════════
# Section 14 — Hypothesis strategies
#
# These generate random polygons for property-based testing of the PIP
# algorithm and slice-masking code.  If Hypothesis is not installed the
# public functions raise ``ModuleNotFoundError`` at call time rather
# than at import time, so the rest of conftest.py (and all deterministic
# tests) still works.
# ═══════════════════════════════════════════════════════════════════════════

if st is not None:

    @st.composite
    def _convex_polygon_strategy_impl(
        draw: st.DrawFn,
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ) -> PointArray:
        """Draw a strictly convex polygon.

        Vertices are placed at random angles on a circle of random
        radius, then sorted by angle.  Sorted angles on a circle always
        produce a convex polygon.  The angular resolution is quantised
        to 0.1° (3600 ticks) to keep the search space tractable.
        """
        n_vertices = draw(st.integers(min_value=min_vertices, max_value=max_vertices))
        angle_ticks = draw(
            st.lists(
                st.integers(min_value=0, max_value=3599),
                min_size=n_vertices,
                max_size=n_vertices,
                unique=True,
            )
        )
        radius_mm = draw(
            st.floats(
                min_value=0.5,
                max_value=20.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        centre_x_mm = draw(
            st.floats(
                min_value=-10.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        centre_y_mm = draw(
            st.floats(
                min_value=-10.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        angle_offset_rad = draw(
            st.floats(
                min_value=0.0,
                max_value=math.tau,
                allow_nan=False,
                allow_infinity=False,
            )
        )

        angles_rad = np.sort(np.asarray(angle_ticks, dtype=np.float64)) * (
            math.tau / 3600.0
        )
        angles_rad = angles_rad + angle_offset_rad

        polygon_xy_mm = np.column_stack(
            (
                centre_x_mm + radius_mm * np.cos(angles_rad),
                centre_y_mm + radius_mm * np.sin(angles_rad),
            )
        ).astype(np.float64, copy=False)

        assume(abs(_polygon_area_signed(polygon_xy_mm)) > 1.0e-6)
        return polygon_xy_mm

    @st.composite
    def _concave_simple_polygon_strategy_impl(
        draw: st.DrawFn,
    ) -> PointArray:
        """Draw a concave but simple (non-self-intersecting) polygon.

        Starts from a convex base polygon (5–10 vertices) and pushes
        one vertex towards the centroid to create a concavity.  The
        ``inset_fraction`` range (0.1–0.65) ensures the vertex moves
        inward without overshooting to the far side, which would risk
        self-intersection.  Hypothesis ``assume()`` filters any
        examples that still manage to self-intersect.
        """
        base_polygon_xy_mm = draw(
            _convex_polygon_strategy_impl(min_vertices=5, max_vertices=10)
        )
        centroid_xy_mm = np.mean(base_polygon_xy_mm, axis=0)
        inset_index = draw(
            st.integers(min_value=0, max_value=len(base_polygon_xy_mm) - 1)
        )
        inset_fraction = draw(
            st.floats(
                min_value=0.1,
                max_value=0.65,
                allow_nan=False,
                allow_infinity=False,
            )
        )

        polygon_xy_mm = base_polygon_xy_mm.copy()
        polygon_xy_mm[inset_index] = centroid_xy_mm + inset_fraction * (
            base_polygon_xy_mm[inset_index] - centroid_xy_mm
        )

        assume(_is_simple_polygon(polygon_xy_mm))
        assume(_is_concave_polygon(polygon_xy_mm))
        return polygon_xy_mm.astype(np.float64, copy=False)

    def convex_polygon_strategy(
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ) -> st.SearchStrategy[PointArray]:
        """Return a Hypothesis strategy for strictly convex polygons."""
        return _convex_polygon_strategy_impl(
            min_vertices=min_vertices,
            max_vertices=max_vertices,
        )

    def simple_polygon_strategy(
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ) -> st.SearchStrategy[PointArray]:
        """Return a Hypothesis strategy for general simple polygons.

        Mixes convex and explicitly concave simple polygons via
        ``st.one_of`` so that slice-masking tests exercise more than
        one polygon family.

        .. note::

            The concave branch internally generates 5–10 vertex
            polygons.  If ``min_vertices`` > 5 or ``max_vertices`` < 5,
            the concave branch's filter may reject most or all examples,
            effectively producing only convex polygons.  This is
            mathematically correct (a concave polygon needs ≥ 4
            vertices) but worth being aware of.
        """
        convex = convex_polygon_strategy(
            min_vertices=min_vertices,
            max_vertices=max_vertices,
        )

        concave = _concave_simple_polygon_strategy_impl().filter(
            lambda p: min_vertices <= len(p) <= max_vertices
        )

        return st.one_of(convex, concave)

else:
    # ------------------------------------------------------------------
    # Stubs when Hypothesis is not installed.  Raise at call time, not
    # import time, so deterministic tests still collect and run.
    # ------------------------------------------------------------------

    def convex_polygon_strategy(  # type: ignore[misc]
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ):
        """Stub — raises because Hypothesis is not installed."""
        raise ModuleNotFoundError(
            "hypothesis is required for convex_polygon_strategy()."
        )

    def simple_polygon_strategy(  # type: ignore[misc]
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ):
        """Stub — raises because Hypothesis is not installed."""
        raise ModuleNotFoundError(
            "hypothesis is required for simple_polygon_strategy()."
        )


# ═══════════════════════════════════════════════════════════════════════════
# Section 15 — Convenience wrapper: contours → Structure
# ═══════════════════════════════════════════════════════════════════════════
#
# The Nelms fixtures in Section 16 return raw contour tuples (factory
# callables).  Many test functions will need to wrap those contours
# into a full Structure before passing them to ``compute_dvh``.
# These wrappers reduce that boilerplate.
# ═══════════════════════════════════════════════════════════════════════════

_NELMS_STRUCTURE_DEFINITIONS: dict[
    str, tuple[str, Callable[[float], tuple[PlanarContour, ...]], int]
] = {
    "sphere": ("nelms_sphere", _make_nelms_sphere_contours, 10),
    "axial_cylinder": (
        "nelms_axial_cylinder",
        _make_nelms_axial_cylinder_contours,
        11,
    ),
    "rotated_cylinder": (
        "nelms_rotated_cylinder",
        _make_nelms_rotated_cylinder_contours,
        12,
    ),
    "axial_cone": ("nelms_axial_cone", _make_nelms_axial_cone_contours, 13),
    "rotated_cone": (
        "nelms_rotated_cone",
        _make_nelms_rotated_cone_contours,
        14,
    ),
}


def _make_nelms_structure(
    shape_key: str,
    spacing_mm: float,
) -> Structure:
    """Build a full ``Structure`` for one of the five Nelms shapes.

    Parameters
    ----------
    shape_key
        One of ``"sphere"``, ``"axial_cylinder"``,
        ``"rotated_cylinder"``, ``"axial_cone"``, ``"rotated_cone"``.
    spacing_mm
        Axial contour slice spacing in mm.
    """
    name, contour_builder, number = _NELMS_STRUCTURE_DEFINITIONS[shape_key]
    contours = contour_builder(spacing_mm)
    return _structure(name, contours, number=number)


# ═══════════════════════════════════════════════════════════════════════════
# Section 16 — Pytest fixtures
#
# FIXTURE OVERVIEW
# ----------------
# Fixture name                    Returns          Pattern
# ─────────────────────────────── ──────────────── ───────────
# unit_square                     PointArray       value
# unit_triangle                   PointArray       value
# concave_l_polygon               PointArray       value
# circle_polygon                  Callable → PA    factory
# nelms_sphere_contours           Callable → ctrs  factory
# nelms_axial_cylinder_contours   Callable → ctrs  factory
# nelms_rotated_cylinder_contours Callable → ctrs  factory
# nelms_axial_cone_contours       Callable → ctrs  factory
# nelms_rotated_cone_contours     Callable → ctrs  factory
# nelms_sphere_structure          Callable → Struc factory
# nelms_axial_cylinder_structure  Callable → Struc factory
# nelms_rotated_cylinder_structure Callable → Struc factory
# nelms_axial_cone_structure      Callable → Struc factory
# nelms_rotated_cone_structure    Callable → Struc factory
# linear_dose_grid                Callable → DG    factory
# uniform_dose_grid               Callable → DG    factory
# structure_with_hole             Callable → Struc factory
# tiny_sphere_contours            Callable → ctrs  factory
# steep_surface_gradient_case     Callable → SDVHC factory
#
# "value" fixtures return a concrete object, the same every time.
# "factory" fixtures return a *callable* — see module docstring.
# ═══════════════════════════════════════════════════════════════════════════


# --- Basic polygon fixtures (value pattern) ---


@pytest.fixture
def unit_square() -> PointArray:
    """A 1 mm × 1 mm square centred at the origin.  Area = 1.0 mm².

    Vertices are counter-clockwise.
    """
    return _as_float64_points(
        [
            (-0.5, -0.5),
            (0.5, -0.5),
            (0.5, 0.5),
            (-0.5, 0.5),
        ]
    )


@pytest.fixture
def unit_triangle() -> PointArray:
    """A right triangle with legs of length 1 mm.  Area = 0.5 mm².

    Vertices are counter-clockwise:  origin → (1, 0) → (0, 1).
    """
    return _as_float64_points(
        [
            (0.0, 0.0),
            (1.0, 0.0),
            (0.0, 1.0),
        ]
    )


@pytest.fixture
def concave_l_polygon() -> PointArray:
    """An L-shaped concave hexagon.  Area = 5.0 mm².

    The L is formed by cutting a 2 × 2 mm square from the top-right
    corner of a 3 × 3 mm square.  Vertices are counter-clockwise.
    This is a minimal concave polygon for testing PIP algorithms that
    might fail on non-convex shapes.
    """
    return _as_float64_points(
        [
            (0.0, 0.0),
            (3.0, 0.0),
            (3.0, 1.0),
            (1.0, 1.0),
            (1.0, 3.0),
            (0.0, 3.0),
        ]
    )


# --- Nelms contour fixtures (factory pattern) ---


@pytest.fixture
def circle_polygon() -> Callable[..., PointArray]:
    """Factory: ``circle_polygon(radius_mm=12.0, n_points=128)``."""
    return _make_circle_polygon


@pytest.fixture
def nelms_sphere_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``nelms_sphere_contours(spacing_mm)`` → contour tuple."""
    return _make_nelms_sphere_contours


@pytest.fixture
def nelms_axial_cylinder_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``nelms_axial_cylinder_contours(spacing_mm)`` → contour tuple."""
    return _make_nelms_axial_cylinder_contours


@pytest.fixture
def nelms_rotated_cylinder_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``nelms_rotated_cylinder_contours(spacing_mm)`` → contour tuple."""
    return _make_nelms_rotated_cylinder_contours


@pytest.fixture
def nelms_axial_cone_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``nelms_axial_cone_contours(spacing_mm)`` → contour tuple."""
    return _make_nelms_axial_cone_contours


@pytest.fixture
def nelms_rotated_cone_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``nelms_rotated_cone_contours(spacing_mm)`` → contour tuple."""
    return _make_nelms_rotated_cone_contours


# --- Nelms structure fixtures (factory pattern) ---
#
# These wrap contours into full Structure objects for tests that call
# compute_dvh directly.  Usage example:
#
#     def test_sphere_volume(nelms_sphere_structure, uniform_dose_grid):
#         structure = nelms_sphere_structure(spacing_mm=1.0)
#         grid = uniform_dose_grid(dose_gy=2.0)
#         result = compute_dvh(structure, grid)
#         ...


@pytest.fixture
def nelms_sphere_structure() -> Callable[..., Structure]:
    """Factory: ``nelms_sphere_structure(spacing_mm)`` → Structure."""

    def _build(spacing_mm: float) -> Structure:
        return _make_nelms_structure("sphere", spacing_mm)

    return _build


@pytest.fixture
def nelms_axial_cylinder_structure() -> Callable[..., Structure]:
    """Factory: ``nelms_axial_cylinder_structure(spacing_mm)`` → Structure."""

    def _build(spacing_mm: float) -> Structure:
        return _make_nelms_structure("axial_cylinder", spacing_mm)

    return _build


@pytest.fixture
def nelms_rotated_cylinder_structure() -> Callable[..., Structure]:
    """Factory: ``nelms_rotated_cylinder_structure(spacing_mm)`` → Structure."""

    def _build(spacing_mm: float) -> Structure:
        return _make_nelms_structure("rotated_cylinder", spacing_mm)

    return _build


@pytest.fixture
def nelms_axial_cone_structure() -> Callable[..., Structure]:
    """Factory: ``nelms_axial_cone_structure(spacing_mm)`` → Structure."""

    def _build(spacing_mm: float) -> Structure:
        return _make_nelms_structure("axial_cone", spacing_mm)

    return _build


@pytest.fixture
def nelms_rotated_cone_structure() -> Callable[..., Structure]:
    """Factory: ``nelms_rotated_cone_structure(spacing_mm)`` → Structure."""

    def _build(spacing_mm: float) -> Structure:
        return _make_nelms_structure("rotated_cone", spacing_mm)

    return _build


# --- Dose-grid fixtures (factory pattern) ---


@pytest.fixture
def linear_dose_grid() -> Callable[..., DoseGrid]:
    """Factory: ``linear_dose_grid(direction, resolution_mm, ...)`` → DoseGrid.

    See ``_make_linear_dose_grid`` for full parameter documentation.
    """
    return _make_linear_dose_grid


@pytest.fixture
def uniform_dose_grid() -> Callable[..., DoseGrid]:
    """Factory: ``uniform_dose_grid(dose_gy, resolution_mm, ...)`` → DoseGrid."""
    return _make_uniform_dose_grid


# --- Special-case fixtures ---


@pytest.fixture
def structure_with_hole() -> Callable[..., Structure]:
    """Factory: ``structure_with_hole(spacing_mm=1.0)`` → annular Structure."""
    return _make_structure_with_hole


@pytest.fixture
def tiny_sphere_contours() -> Callable[..., tuple[PlanarContour, ...]]:
    """Factory: ``tiny_sphere_contours(radius_mm=2.0, spacing_mm=1.0)``."""
    return _make_tiny_sphere_contours


@pytest.fixture
def steep_surface_gradient_case() -> Callable[..., SyntheticDVHCase]:
    """Factory: ``steep_surface_gradient_case(contour_spacing_mm=0.5)``.

    Returns a ``SyntheticDVHCase`` bundling structure, dose grid, and
    expected surface-dose values for a small sphere in a steep gradient.
    Now a factory (not a fixed value) so that tests can sweep contour
    spacing for Pepin-style precision analysis.
    """
    return _make_steep_surface_gradient_case


# ═══════════════════════════════════════════════════════════════════════════
# Section 17 — Module-level self-consistency checks
#
# These assertions run once at import time (i.e. before any test is
# collected).  If any check fails, pytest reports an import error on
# this conftest, which immediately tells you the fixture infrastructure
# itself is broken — no downstream test can be trusted.
#
# The checks are deliberately lightweight: signed-area computations
# and vertex-count checks, nothing that allocates large arrays or
# invokes heavy computation.
# ═══════════════════════════════════════════════════════════════════════════


def _validate_fixture_geometry() -> None:
    """Self-check the ground-truth fixtures for internal consistency.

    Raises ``AssertionError`` with a descriptive message if any check
    fails.
    """
    # --- Basic polygon areas ---
    _unit_sq = _as_float64_points([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])
    _sq_area = _polygon_area_signed(_unit_sq)
    assert math.isclose(
        _sq_area, 1.0, rel_tol=1e-12
    ), f"Unit square signed area should be +1.0, got {_sq_area}"

    _unit_tri = _as_float64_points([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
    _tri_area = _polygon_area_signed(_unit_tri)
    assert math.isclose(
        _tri_area, 0.5, rel_tol=1e-12
    ), f"Unit triangle signed area should be +0.5, got {_tri_area}"

    _l_poly = _as_float64_points(
        [(0.0, 0.0), (3.0, 0.0), (3.0, 1.0), (1.0, 1.0), (1.0, 3.0), (0.0, 3.0)]
    )
    _l_area = _polygon_area_signed(_l_poly)
    assert math.isclose(
        _l_area, 5.0, rel_tol=1e-12
    ), f"L-polygon signed area should be +5.0, got {_l_area}"

    # --- All basic polygons are counter-clockwise (positive signed area) ---
    assert _sq_area > 0, "Unit square should be counter-clockwise"
    assert _tri_area > 0, "Unit triangle should be counter-clockwise"
    assert _l_area > 0, "L-polygon should be counter-clockwise"

    # --- Concavity check: the L-polygon must be detected as concave ---
    assert _is_concave_polygon(
        _l_poly
    ), "L-polygon should be concave (has a reflex angle)"

    # --- Nelms sphere at z = 0 has radius = NELMS_RADIUS_MM ---
    _sphere_contours = _make_nelms_sphere_contours(spacing_mm=1.0)
    _equatorial = [c for c in _sphere_contours if abs(c.z_mm) < 0.01]
    assert (
        len(_equatorial) == 1
    ), f"Expected exactly one equatorial slice, got {len(_equatorial)}"
    _eq_points = _equatorial[0].points_xy_mm
    _eq_radii = np.sqrt(_eq_points[:, 0] ** 2 + _eq_points[:, 1] ** 2)
    assert np.allclose(_eq_radii, NELMS_RADIUS_MM, atol=1e-9), (
        f"Equatorial radius should be {NELMS_RADIUS_MM} mm, "
        f"got mean {np.mean(_eq_radii):.6f}"
    )

    # --- Sphere endpoints must be tiny polygons, not large circles ---
    _first = _sphere_contours[0]
    _last = _sphere_contours[-1]
    _first_max_r = float(
        np.max(np.sqrt(_first.points_xy_mm[:, 0] ** 2 + _first.points_xy_mm[:, 1] ** 2))
    )
    _last_max_r = float(
        np.max(np.sqrt(_last.points_xy_mm[:, 0] ** 2 + _last.points_xy_mm[:, 1] ** 2))
    )
    assert (
        _first_max_r < 0.01
    ), f"First sphere slice should be a tiny polygon, radius={_first_max_r}"
    assert (
        _last_max_r < 0.01
    ), f"Last sphere slice should be a tiny polygon, radius={_last_max_r}"

    # --- Rotated cylinder slices must be rectangles (4 vertices) ---
    _rot_cyl = _make_nelms_rotated_cylinder_contours(spacing_mm=2.0)
    for _rc_contour in _rot_cyl:
        assert _rc_contour.points_xy_mm.shape == (4, 2), (
            f"Rotated cylinder slice at z={_rc_contour.z_mm} has "
            f"{_rc_contour.points_xy_mm.shape[0]} vertices, expected 4"
        )

    # --- Slice position generator: endpoints present and exact ---
    _positions = _slice_positions_with_end_slices(12.0, 2.5)
    assert float(_positions[0]) == -12.0, "First position must be -12.0"
    assert float(_positions[-1]) == 12.0, "Last position must be +12.0"

    # --- Dose grid axis convention ---
    _grid = _make_linear_dose_grid("AP", resolution_mm=1.0, grid_extent_mm=5.0)
    _x, _y, _z = _grid.axes_mm
    # In an AP gradient, dose increases with y.  Check that the value at
    # (ix=mid, iy=last, iz=mid) > value at (ix=mid, iy=0, iz=mid).
    _mid_x = _x.size // 2
    _mid_z = _z.size // 2
    assert (
        _grid.values_gy[_mid_x, -1, _mid_z] > _grid.values_gy[_mid_x, 0, _mid_z]
    ), "AP gradient should increase with y-index"

    _grid_si = _make_linear_dose_grid("SI", resolution_mm=1.0, grid_extent_mm=5.0)
    assert (
        _grid_si.values_gy[_mid_x, _mid_x, -1] > _grid_si.values_gy[_mid_x, _mid_x, 0]
    ), "SI gradient should increase with z-index"


# Run the self-checks immediately at import time.
_validate_fixture_geometry()
