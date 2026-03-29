"""Tests for Contour, PlanarRegion, and ContourROI (RFC section 6.7)."""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh._types._contour import (
    CombinationMode,
    Contour,
    ContourROI,
    CoordinateFrame,
    PlanarRegion,
)
from pymedphys._dvh._types._roi_ref import ROIRef


class TestContour:
    """Tests for the raw Contour type."""

    def test_accepts_valid_triangle(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        c = Contour(points_xy=pts, z_mm=10.0)
        assert c.z_mm == 10.0
        assert c.points_xy.shape == (3, 2)

    def test_rejects_less_than_3_points(self) -> None:
        pts = np.array([[0, 0], [1, 0]], dtype=np.float64)
        with pytest.raises(ValueError, match="3"):
            Contour(points_xy=pts, z_mm=0.0)

    def test_rejects_wrong_shape(self) -> None:
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
        with pytest.raises(ValueError, match="N, 2"):
            Contour(points_xy=pts, z_mm=0.0)

    def test_rejects_1d_array(self) -> None:
        pts = np.array([0, 1, 2, 3, 4, 5], dtype=np.float64)
        with pytest.raises(ValueError, match="N, 2"):
            Contour(points_xy=pts, z_mm=0.0)

    def test_rejects_non_finite_z(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        with pytest.raises(ValueError, match="finite"):
            Contour(points_xy=pts, z_mm=float("inf"))

    def test_rejects_nan_z(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        with pytest.raises(ValueError, match="finite"):
            Contour(points_xy=pts, z_mm=float("nan"))

    def test_array_is_read_only(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        c = Contour(points_xy=pts, z_mm=0.0)
        with pytest.raises(ValueError, match="read-only"):
            c.points_xy[0, 0] = 999.0

    def test_defensive_copy(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        c = Contour(points_xy=pts, z_mm=0.0)
        pts[0, 0] = 999.0
        assert c.points_xy[0, 0] != 999.0

    def test_eq_with_same_data(self) -> None:
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        c1 = Contour(points_xy=pts, z_mm=5.0)
        c2 = Contour(points_xy=pts.copy(), z_mm=5.0)
        assert c1 == c2

    def test_eq_different_data(self) -> None:
        pts1 = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
        pts2 = np.array([[0, 0], [2, 0], [0, 2]], dtype=np.float64)
        c1 = Contour(points_xy=pts1, z_mm=5.0)
        c2 = Contour(points_xy=pts2, z_mm=5.0)
        assert c1 != c2


class TestPlanarRegion:
    """Tests for the PlanarRegion type."""

    def test_stores_exterior(self) -> None:
        ext = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        pr = PlanarRegion(exterior_xy_mm=ext)
        np.testing.assert_array_equal(pr.exterior_xy_mm, ext)

    def test_stores_holes(self) -> None:
        ext = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float64)
        # Hole must be CW (clockwise = negative signed area)
        hole = np.array([[2, 8], [8, 8], [8, 2], [2, 2]], dtype=np.float64)
        pr = PlanarRegion(exterior_xy_mm=ext, holes_xy_mm=(hole,))
        assert len(pr.holes_xy_mm) == 1

    def test_defensive_copy_exterior(self) -> None:
        ext = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        pr = PlanarRegion(exterior_xy_mm=ext)
        ext[0, 0] = 999.0
        assert pr.exterior_xy_mm[0, 0] != 999.0

    def test_exterior_is_read_only(self) -> None:
        ext = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        pr = PlanarRegion(exterior_xy_mm=ext)
        with pytest.raises(ValueError, match="read-only"):
            pr.exterior_xy_mm[0, 0] = 999.0

    def test_eq_same_data(self) -> None:
        ext = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        pr1 = PlanarRegion(exterior_xy_mm=ext)
        pr2 = PlanarRegion(exterior_xy_mm=ext.copy())
        assert pr1 == pr2

    def test_eq_different_holes_count(self) -> None:
        ext = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float64)
        # CW hole (negative signed area)
        hole = np.array([[2, 8], [8, 8], [8, 2], [2, 2]], dtype=np.float64)
        pr1 = PlanarRegion(exterior_xy_mm=ext)
        pr2 = PlanarRegion(exterior_xy_mm=ext, holes_xy_mm=(hole,))
        assert pr1 != pr2


class TestContourROI:
    """Tests for the ContourROI type."""

    def _make_region(self) -> PlanarRegion:
        ext = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        return PlanarRegion(exterior_xy_mm=ext)

    def _make_roi(self) -> ROIRef:
        return ROIRef(name="PTV")

    def test_valid_construction(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (2.5, (region,)),
            ),
        )
        assert croi.num_slices == 2

    def test_rejects_empty_slices(self) -> None:
        with pytest.raises(ValueError, match="no slices"):
            ContourROI(roi=self._make_roi(), slices=())

    def test_rejects_unsorted_z_values(self) -> None:
        region = self._make_region()
        with pytest.raises(ValueError, match="sorted"):
            ContourROI(
                roi=self._make_roi(),
                slices=(
                    (5.0, (region,)),
                    (2.5, (region,)),
                ),
            )

    def test_rejects_duplicate_z_values(self) -> None:
        region = self._make_region()
        with pytest.raises(ValueError, match="Duplicate"):
            ContourROI(
                roi=self._make_roi(),
                slices=(
                    (2.5, (region,)),
                    (2.5, (region,)),
                ),
            )

    def test_rejects_empty_regions_at_slice(self) -> None:
        with pytest.raises(ValueError, match="Empty"):
            ContourROI(
                roi=self._make_roi(),
                slices=((0.0, ()),),
            )

    def test_z_values_mm(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (2.5, (region,)),
                (5.0, (region,)),
            ),
        )
        assert croi.z_values_mm == (0.0, 2.5, 5.0)

    def test_z_extent_mm(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (5.0, (region,)),
            ),
        )
        assert croi.z_extent_mm == 5.0

    def test_mean_slice_spacing_mm(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (2.5, (region,)),
                (5.0, (region,)),
            ),
        )
        assert croi.mean_slice_spacing_mm == pytest.approx(2.5)

    def test_mean_slice_spacing_none_for_single_slice(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=((0.0, (region,)),),
        )
        assert croi.mean_slice_spacing_mm is None

    def test_combination_mode_default(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=((0.0, (region,)),),
        )
        assert croi.combination_mode == CombinationMode.AUTO

    def test_coordinate_frame_default(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=((0.0, (region,)),),
        )
        assert croi.coordinate_frame == CoordinateFrame.DICOM_PATIENT

    def test_nonuniform_slice_spacing(self) -> None:
        """D6: Non-uniform slice spacing should be supported and reported."""
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (2.0, (region,)),
                (5.0, (region,)),  # gap of 3.0, not 2.0
            ),
        )
        assert croi.mean_slice_spacing_mm == pytest.approx(2.5)
        assert croi.slice_spacings_mm == pytest.approx((2.0, 3.0))
        assert croi.is_uniform_spacing is False

    def test_uniform_slice_spacing_detected(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=(
                (0.0, (region,)),
                (2.5, (region,)),
                (5.0, (region,)),
            ),
        )
        assert croi.is_uniform_spacing is True

    def test_single_slice_spacing_is_none(self) -> None:
        region = self._make_region()
        croi = ContourROI(
            roi=self._make_roi(),
            slices=((0.0, (region,)),),
        )
        assert croi.slice_spacings_mm is None
        assert croi.is_uniform_spacing is None


class TestPlanarRegionValidation:
    """Tests for PlanarRegion winding validation (D7)."""

    def test_rejects_cw_exterior(self) -> None:
        """Exterior must be CCW (positive signed area)."""
        # CW square (negative area)
        ext = np.array([[0, 0], [0, 1], [1, 1], [1, 0]], dtype=np.float64)
        with pytest.raises(ValueError, match="CCW"):
            PlanarRegion(exterior_xy_mm=ext)

    def test_rejects_ccw_hole(self) -> None:
        """Holes must be CW (negative signed area)."""
        ext = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float64)
        # CCW hole (positive area — wrong winding)
        hole = np.array([[2, 2], [8, 2], [8, 8], [2, 8]], dtype=np.float64)
        with pytest.raises(ValueError, match="CW"):
            PlanarRegion(exterior_xy_mm=ext, holes_xy_mm=(hole,))

    def test_accepts_valid_ccw_exterior_cw_hole(self) -> None:
        ext = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float64)
        # CW hole (clockwise = negative signed area)
        hole = np.array([[2, 8], [8, 8], [8, 2], [2, 2]], dtype=np.float64)
        pr = PlanarRegion(exterior_xy_mm=ext, holes_xy_mm=(hole,))
        assert len(pr.holes_xy_mm) == 1
