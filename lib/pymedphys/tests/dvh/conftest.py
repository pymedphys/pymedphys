"""Shared DVH test fixtures for the PyMedPhys MVP.

This provides every shared fixture used by the DVH test suite.  It is
intentionally self-contained: while the ``pymedphys._dvh`` package is still
under construction, local fallback dataclasses keep this module importable
and executable without the production type definitions.  Once
``_dvh.types`` exists the fallback is bypassed automatically.

Geometry builders and computational helpers have been extracted to
``_fixture_geometry.py`` to keep this file within the project line-count
guidelines; they are re-imported below for use by fixtures and the
module-level self-consistency checks.

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
from typing import TYPE_CHECKING, Any, Callable

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

if TYPE_CHECKING:
    from hypothesis.strategies import DrawFn

# ---------------------------------------------------------------------------
# Geometry builders and helpers (extracted to _fixture_geometry.py)
# ---------------------------------------------------------------------------
from pymedphys.tests.dvh._fixture_geometry import (
    NELMS_RADIUS_MM,
    PointArray,
    SyntheticDVHCase,
    _as_float64_points,
    _is_concave_polygon,
    _is_simple_polygon,
    _make_circle_polygon,
    _make_linear_dose_grid,
    _make_nelms_axial_cone_contours,
    _make_nelms_axial_cylinder_contours,
    _make_nelms_rotated_cone_contours,
    _make_nelms_rotated_cylinder_contours,
    _make_nelms_sphere_contours,
    _make_nelms_structure,
    _make_steep_surface_gradient_case,
    _make_structure_with_hole,
    _make_tiny_sphere_contours,
    _make_uniform_dose_grid,
    _polygon_area_signed,
    _slice_positions_with_end_slices,
)

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
        draw: DrawFn,
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
        draw: DrawFn,
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

    def convex_polygon_strategy(  # type: ignore[no-redef]
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ) -> Any:
        """Return a Hypothesis strategy for strictly convex polygons."""
        return _convex_polygon_strategy_impl(
            min_vertices=min_vertices,
            max_vertices=max_vertices,
        )

    def simple_polygon_strategy(  # type: ignore[no-redef]
        *,
        min_vertices: int = 3,
        max_vertices: int = 10,
    ) -> Any:
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

    # --- Rotated cylinder slices must be rectangles (4 unique vertices + close) ---
    _rot_cyl = _make_nelms_rotated_cylinder_contours(spacing_mm=2.0)
    for _rc_contour in _rot_cyl:
        assert _rc_contour.points_xy_mm.shape == (5, 2), (
            f"Rotated cylinder slice at z={_rc_contour.z_mm} has "
            f"{_rc_contour.points_xy_mm.shape[0]} vertices, expected 5 "
            "(4 unique vertices + 1 closing vertex)"
        )
        np.testing.assert_allclose(
            _rc_contour.points_xy_mm[0],
            _rc_contour.points_xy_mm[-1],
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
