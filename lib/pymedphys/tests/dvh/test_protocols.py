"""Tests for pymedphys._dvh.protocols — strategy protocol conformance.

These tests verify that the ``@runtime_checkable`` protocols correctly
identify conforming and non-conforming objects via ``isinstance``.

Full signature conformance (parameter types, return types) is enforced
by pyright at static analysis time.  The runtime checks only verify
that ``__call__`` exists with the right positional arity.
"""

from __future__ import annotations

import numpy as np

from pymedphys._dvh.protocols import (
    EndCapStrategy,
    InterSliceStrategy,
    PointInPolygonStrategy,
)
from pymedphys._dvh.types import PlanarContour


# ===================================================================
# PointInPolygonStrategy
# ===================================================================


class TestPointInPolygonStrategyProtocol:
    """Verify PointInPolygonStrategy runtime-checkable behaviour."""

    def test_conforming_function_is_recognised(self) -> None:
        def winding_number(
            query_points_xy_mm: np.ndarray,
            contour_xy_mm: np.ndarray,
            /,
        ) -> np.ndarray:
            return np.ones(len(query_points_xy_mm), dtype=bool)

        assert isinstance(winding_number, PointInPolygonStrategy)

    def test_conforming_callable_class_is_recognised(self) -> None:
        class WindingNumber:
            def __call__(
                self,
                query_points_xy_mm: np.ndarray,
                contour_xy_mm: np.ndarray,
                /,
            ) -> np.ndarray:
                return np.ones(len(query_points_xy_mm), dtype=bool)

        assert isinstance(WindingNumber(), PointInPolygonStrategy)

    def test_non_callable_is_not_recognised(self) -> None:
        assert not isinstance("not callable", PointInPolygonStrategy)
        assert not isinstance(42, PointInPolygonStrategy)


# ===================================================================
# InterSliceStrategy
# ===================================================================


class TestInterSliceStrategyProtocol:
    """Verify InterSliceStrategy runtime-checkable behaviour."""

    def test_conforming_function_is_recognised(self) -> None:
        # shape_based is the preferred MVP inter-slice strategy; it blends
        # upper and lower contour vertices at the target z position.
        def shape_based(
            lower_contour: PlanarContour,
            upper_contour: PlanarContour,
            z_mm: float,
            /,
        ) -> PlanarContour:
            alpha = (z_mm - lower_contour.z_mm) / (
                upper_contour.z_mm - lower_contour.z_mm
            )
            blended = (1 - alpha) * lower_contour.points_xy_mm + alpha * upper_contour.points_xy_mm
            return PlanarContour(z_mm=z_mm, points_xy_mm=blended)

        assert isinstance(shape_based, InterSliceStrategy)

    def test_non_callable_is_not_recognised(self) -> None:
        assert not isinstance(None, InterSliceStrategy)


# ===================================================================
# EndCapStrategy
# ===================================================================


class TestEndCapStrategyProtocol:
    """Verify EndCapStrategy runtime-checkable behaviour."""

    def test_conforming_function_is_recognised(self) -> None:
        def half_slab(
            contour: PlanarContour,
            neighbour_spacing_mm: float,
            is_superior: bool,
            /,
        ) -> tuple[float, float]:
            half = neighbour_spacing_mm / 2.0
            return (contour.z_mm - half, contour.z_mm + half)

        assert isinstance(half_slab, EndCapStrategy)

    def test_non_callable_is_not_recognised(self) -> None:
        assert not isinstance([], EndCapStrategy)
