"""Tests for pymedphys._dvh.types — core DVH data model.

Organised by class under test:

- PlanarContour
- Structure
- DoseGrid
- DVHResult

Strategy protocol tests live in ``test_protocols.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from pymedphys._dvh.types import (
    DVHResult,
    DoseGrid,
    PlanarContour,
    Structure,
)


# ===================================================================
# Helpers
# ===================================================================


def _triangle(z: float = 0.0) -> PlanarContour:
    """Minimal valid contour for tests that don't care about geometry."""
    return PlanarContour(
        z_mm=z,
        points_xy_mm=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]),
    )


def _make_dvh_result(**overrides: object) -> DVHResult:
    """Construct a valid DVHResult, overriding individual fields as needed."""
    defaults: dict[str, object] = {
        "structure_name": "PTV",
        "dose_bins_gy": np.array([0.0, 1.0, 2.0]),
        "cumulative_volume_cm3": np.array([10.0, 7.5, 0.0]),
        "total_volume_cm3": 10.0,
        "voxel_count": 100,
        "bin_width_gy": 1.0,
        "supersampling_factor": (5, 5, 5),
        "point_in_polygon_method": "winding_number",
        "interslice_method": "right_prism",
        "endcap_method": "half_slab",
    }
    defaults.update(overrides)
    return DVHResult(**defaults)  # type: ignore[arg-type]


def _make_dose_grid(
    *,
    nx: int = 3,
    ny: int = 4,
    nz: int = 2,
    dx: float = 2.5,
    dy: float = 2.5,
    dz: float = 3.0,
    fill: float = 1.0,
) -> DoseGrid:
    """Construct a valid DoseGrid with uniform spacing and constant dose."""
    x = np.arange(nx, dtype=float) * dx
    y = np.arange(ny, dtype=float) * dy
    z = np.arange(nz, dtype=float) * dz
    values = np.full((nx, ny, nz), fill)
    return DoseGrid(axes_mm=(x, y, z), values_gy=values)


# ===================================================================
# PlanarContour
# ===================================================================


class TestPlanarContourAutoClose:
    """Verify polygon auto-closing behaviour."""

    def test_open_polygon_is_closed(self) -> None:
        contour = PlanarContour(
            z_mm=12.5,
            points_xy_mm=np.array(
                [
                    [0.0, 0.0],
                    [3.0, 0.0],
                    [3.0, 2.0],
                    [0.0, 2.0],
                ]
            ),
        )
        assert contour.points_xy_mm.shape == (5, 2)
        np.testing.assert_allclose(contour.points_xy_mm[0], contour.points_xy_mm[-1])

    def test_already_closed_polygon_is_not_double_closed(self) -> None:
        contour = PlanarContour(
            z_mm=0.0,
            points_xy_mm=np.array(
                [
                    [0.0, 0.0],
                    [1.0, 0.0],
                    [1.0, 1.0],
                    [0.0, 0.0],
                ]
            ),
        )
        # 3 unique vertices + 1 closing = shape (4, 2), not (5, 2)
        assert contour.points_xy_mm.shape == (4, 2)
        np.testing.assert_allclose(contour.points_xy_mm[0], contour.points_xy_mm[-1])


class TestPlanarContourValidation:
    """Verify input validation catches malformed contour data."""

    def test_rejects_flat_array(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            PlanarContour(z_mm=0.0, points_xy_mm=np.array([0.0, 1.0, 2.0]))

    def test_rejects_wrong_column_count(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            PlanarContour(
                z_mm=0.0,
                points_xy_mm=np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]),
            )

    def test_rejects_fewer_than_three_vertices(self) -> None:
        with pytest.raises(ValueError, match="at least 3"):
            PlanarContour(
                z_mm=0.0,
                points_xy_mm=np.array([[0.0, 0.0], [1.0, 0.0]]),
            )

    def test_rejects_invalid_geometric_type(self) -> None:
        with pytest.raises(ValueError, match="geometric_type"):
            PlanarContour(
                z_mm=0.0,
                points_xy_mm=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]),
                geometric_type="OPEN_NONPLANAR",
            )

    def test_accepts_closed_planar_xor(self) -> None:
        contour = PlanarContour(
            z_mm=0.0,
            points_xy_mm=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]),
            geometric_type="CLOSED_PLANAR_XOR",
        )
        assert contour.geometric_type == "CLOSED_PLANAR_XOR"


class TestPlanarContourImmutability:
    """Verify that the points array is read-only after construction."""

    def test_points_array_is_not_writeable(self) -> None:
        contour = _triangle()
        assert contour.points_xy_mm.flags.writeable is False

    def test_writing_to_points_raises(self) -> None:
        contour = _triangle()
        with pytest.raises(ValueError, match="read-only"):
            contour.points_xy_mm[0, 0] = 999.0


class TestPlanarContourNormalisation:
    """Verify dtype and value normalisation."""

    def test_z_mm_is_float(self) -> None:
        contour = PlanarContour(
            z_mm=5,  # type: ignore[arg-type]  # intentional int
            points_xy_mm=np.array([[0, 0], [1, 0], [1, 1]]),
        )
        assert isinstance(contour.z_mm, float)
        assert contour.z_mm == 5.0

    def test_points_are_float64(self) -> None:
        contour = PlanarContour(
            z_mm=0.0,
            points_xy_mm=np.array([[0, 0], [1, 0], [1, 1]], dtype=np.int32),
        )
        assert contour.points_xy_mm.dtype == np.float64


# ===================================================================
# Structure
# ===================================================================


class TestStructureSorting:
    """Verify contours are sorted by z_mm on construction."""

    def test_contours_sorted_by_z(self) -> None:
        c1 = _triangle(z=5.0)
        c2 = _triangle(z=1.0)
        c3 = _triangle(z=3.0)

        structure = Structure(name="PTV", number=7, contours=(c1, c2, c3))
        assert [c.z_mm for c in structure.contours] == [1.0, 3.0, 5.0]


class TestStructureValidation:
    """Verify validation of Structure fields."""

    def test_rejects_invalid_combination_mode(self) -> None:
        with pytest.raises(ValueError, match="combination_mode"):
            Structure(
                name="PTV",
                number=1,
                contours=(_triangle(),),
                combination_mode="bogus",
            )

    def test_rejects_empty_coordinate_frame(self) -> None:
        with pytest.raises(ValueError, match="coordinate_frame"):
            Structure(
                name="PTV",
                number=1,
                contours=(_triangle(),),
                coordinate_frame="",
            )

    def test_rejects_non_planar_contour_items(self) -> None:
        with pytest.raises(TypeError, match="PlanarContour"):
            Structure(
                name="PTV",
                number=1,
                contours=("not a contour",),  # type: ignore[arg-type]
            )

    def test_accepts_all_valid_combination_modes(self) -> None:
        for mode in ("auto", "xor", "slice_union", "vendor_compat_xor"):
            s = Structure(
                name="ROI",
                number=1,
                contours=(_triangle(),),
                combination_mode=mode,
            )
            assert s.combination_mode == mode

    def test_colour_rgb_validation(self) -> None:
        s = Structure(
            name="ROI",
            number=1,
            contours=(_triangle(),),
            colour_rgb=(255, 0, 128),
        )
        assert s.colour_rgb == (255, 0, 128)

    def test_colour_rgb_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="0..255"):
            Structure(
                name="ROI",
                number=1,
                contours=(_triangle(),),
                colour_rgb=(256, 0, 0),
            )


class TestStructureZExtent:
    """Verify the z_extent_mm convenience property."""

    def test_z_extent_from_multiple_contours(self) -> None:
        c1 = _triangle(z=1.0)
        c2 = _triangle(z=5.0)
        c3 = _triangle(z=3.0)
        structure = Structure(name="PTV", number=1, contours=(c1, c2, c3))

        z_lo, z_hi = structure.z_extent_mm
        assert z_lo == 1.0
        assert z_hi == 5.0

    def test_z_extent_single_contour(self) -> None:
        structure = Structure(name="PTV", number=1, contours=(_triangle(z=7.5),))
        z_lo, z_hi = structure.z_extent_mm
        assert z_lo == 7.5
        assert z_hi == 7.5

    def test_z_extent_raises_for_no_contours(self) -> None:
        structure = Structure(name="PTV", number=1, contours=())
        with pytest.raises(ValueError, match="no contours"):
            _ = structure.z_extent_mm


# ===================================================================
# DoseGrid
# ===================================================================


class TestDoseGridConstruction:
    """Verify that a well-formed DoseGrid constructs successfully."""

    def test_valid_grid_preserves_shape(self) -> None:
        grid = _make_dose_grid(nx=3, ny=4, nz=2)
        assert grid.values_gy.shape == (3, 4, 2)
        assert grid.shape == (3, 4, 2)

    def test_axes_are_preserved(self) -> None:
        grid = _make_dose_grid(nx=3, ny=4, nz=2, dx=2.5, dy=2.5, dz=3.0)
        np.testing.assert_allclose(grid.axes_mm[0], [0.0, 2.5, 5.0])
        np.testing.assert_allclose(grid.axes_mm[1], [0.0, 2.5, 5.0, 7.5])
        np.testing.assert_allclose(grid.axes_mm[2], [0.0, 3.0])


class TestDoseGridShapeValidation:
    """Verify shape-related rejection."""

    def test_rejects_shape_mismatch(self) -> None:
        x = np.array([0.0, 1.0])
        y = np.array([0.0, 1.0, 2.0])
        z = np.array([0.0])
        values = np.zeros((2, 2, 1))  # should be (2, 3, 1)

        with pytest.raises(ValueError, match="shape"):
            DoseGrid(axes_mm=(x, y, z), values_gy=values)

    def test_rejects_wrong_axis_count(self) -> None:
        with pytest.raises(ValueError, match="three axes"):
            DoseGrid(
                axes_mm=(np.array([0.0, 1.0]), np.array([0.0, 1.0])),  # type: ignore[arg-type]
                values_gy=np.zeros((2, 2, 1)),
            )


class TestDoseGridMonotonicity:
    """Verify that axes must be monotonically increasing."""

    def test_rejects_non_monotonic_axis(self) -> None:
        x = np.array([0.0, 2.0, 1.0])  # not monotonic
        y = np.array([0.0, 1.0, 2.0])
        z = np.array([0.0, 1.0])
        values = np.zeros((3, 3, 2))

        with pytest.raises(ValueError, match="monotonically increasing"):
            DoseGrid(axes_mm=(x, y, z), values_gy=values)

    def test_rejects_constant_axis(self) -> None:
        x = np.array([1.0, 1.0, 1.0])  # constant — diffs are zero
        y = np.array([0.0, 1.0, 2.0])
        z = np.array([0.0, 1.0])
        values = np.zeros((3, 3, 2))

        with pytest.raises(ValueError, match="monotonically increasing"):
            DoseGrid(axes_mm=(x, y, z), values_gy=values)


class TestDoseGridUniformSpacing:
    """Verify that the MVP rejects non-uniformly spaced axes."""

    def test_rejects_non_uniform_axis(self) -> None:
        x = np.array([0.0, 1.0, 3.0])  # spacing 1.0, then 2.0
        y = np.array([0.0, 1.0, 2.0])
        z = np.array([0.0, 1.0])
        values = np.zeros((3, 3, 2))

        with pytest.raises(ValueError, match="uniformly spaced"):
            DoseGrid(axes_mm=(x, y, z), values_gy=values)

    def test_accepts_single_point_axis(self) -> None:
        """A single-point axis is trivially uniform."""
        x = np.array([5.0])
        y = np.array([0.0, 1.0])
        z = np.array([0.0, 1.0])
        values = np.ones((1, 2, 2))

        grid = DoseGrid(axes_mm=(x, y, z), values_gy=values)
        assert grid.shape == (1, 2, 2)

    def test_accepts_two_point_axis(self) -> None:
        """Two-point axes are trivially uniform."""
        grid = _make_dose_grid(nx=2, ny=2, nz=2)
        assert grid.shape == (2, 2, 2)


class TestDoseGridNonNegativeDose:
    """Verify that negative dose values are rejected."""

    def test_rejects_negative_dose(self) -> None:
        x = np.array([0.0, 1.0])
        y = np.array([0.0, 1.0])
        z = np.array([0.0, 1.0])
        values = np.full((2, 2, 2), -0.01)

        with pytest.raises(ValueError, match="non-negative"):
            DoseGrid(axes_mm=(x, y, z), values_gy=values)

    def test_accepts_zero_dose(self) -> None:
        grid = _make_dose_grid(fill=0.0)
        assert np.all(grid.values_gy == 0.0)


class TestDoseGridImmutability:
    """Verify that grid arrays are read-only after construction."""

    def test_values_array_is_not_writeable(self) -> None:
        grid = _make_dose_grid()
        assert grid.values_gy.flags.writeable is False

    def test_axis_arrays_are_not_writeable(self) -> None:
        grid = _make_dose_grid()
        for axis in grid.axes_mm:
            assert axis.flags.writeable is False

    def test_writing_to_values_raises(self) -> None:
        grid = _make_dose_grid()
        with pytest.raises(ValueError, match="read-only"):
            grid.values_gy[0, 0, 0] = 1.0

    def test_defensive_copy_of_input_arrays(self) -> None:
        """DoseGrid must not alias the caller's arrays."""
        x = np.array([-10.0, 0.0, 10.0])
        y = np.array([-20.0, 0.0, 20.0])
        z = np.array([-30.0, 0.0, 30.0])
        values = np.arange(27, dtype=float).reshape(3, 3, 3)

        x_orig = x.copy()
        y_orig = y.copy()
        z_orig = z.copy()
        values_orig = values.copy()

        grid = DoseGrid(axes_mm=(x, y, z), values_gy=values)

        # Mutate the original arrays after constructing the grid.
        x += 1000.0
        y += 1000.0
        z += 1000.0
        values[:] = -1.0

        # The grid must remain unchanged – implementation must defensively copy.
        for axis, axis_orig in zip(grid.axes_mm, (x_orig, y_orig, z_orig)):
            np.testing.assert_array_equal(axis, axis_orig)

        np.testing.assert_array_equal(grid.values_gy, values_orig)
            grid.values_gy[0, 0, 0] = 999.0


class TestDoseGridProperties:
    """Verify convenience properties on DoseGrid."""

    def test_spacing_mm(self) -> None:
        grid = _make_dose_grid(dx=2.5, dy=3.0, dz=1.5)
        dx, dy, dz = grid.spacing_mm
        assert pytest.approx(dx) == 2.5
        assert pytest.approx(dy) == 3.0
        assert pytest.approx(dz) == 1.5

    def test_spacing_mm_single_point_axis(self) -> None:
        x = np.array([5.0])
        y = np.array([0.0, 2.0])
        z = np.array([0.0, 3.0])
        grid = DoseGrid(axes_mm=(x, y, z), values_gy=np.ones((1, 2, 2)))
        dx, dy, dz = grid.spacing_mm
        assert dx == 0.0
        assert pytest.approx(dy) == 2.0
        assert pytest.approx(dz) == 3.0

    def test_extent_mm(self) -> None:
        grid = _make_dose_grid(nx=3, ny=4, nz=2, dx=2.5, dy=2.5, dz=3.0)
        (x_lo, x_hi), (y_lo, y_hi), (z_lo, z_hi) = grid.extent_mm
        assert pytest.approx(x_lo) == 0.0
        assert pytest.approx(x_hi) == 5.0
        assert pytest.approx(y_lo) == 0.0
        assert pytest.approx(y_hi) == 7.5
        assert pytest.approx(z_lo) == 0.0
        assert pytest.approx(z_hi) == 3.0

    def test_origin_mm(self) -> None:
        grid = _make_dose_grid()
        assert grid.origin_mm == (0.0, 0.0, 0.0)


# ===================================================================
# DVHResult
# ===================================================================


class TestDVHResultConstruction:
    """Verify valid construction and semantics documentation."""

    def test_valid_construction(self) -> None:
        result = _make_dvh_result()
        np.testing.assert_allclose(result.cumulative_volume_cm3, [10.0, 7.5, 0.0])
        assert result.structure_name == "PTV"
        assert result.point_in_polygon_method == "winding_number"
        assert result.supersampling_factor == (5, 5, 5)

    def test_cumulative_bin_semantics_documented(self) -> None:
        assert "dose_bins_gy[i]" in DVHResult.cumulative_bin_semantics
        assert "cumulative_volume_cm3[i]" in DVHResult.cumulative_bin_semantics
        assert "at least" in DVHResult.cumulative_bin_semantics


class TestDVHResultValidation:
    """Verify all validation paths in DVHResult.__post_init__."""

    def test_rejects_mismatched_array_shapes(self) -> None:
        with pytest.raises(ValueError, match="same shape"):
            _make_dvh_result(
                dose_bins_gy=np.array([0.0, 1.0]),
                cumulative_volume_cm3=np.array([10.0, 7.5, 0.0]),
            )

    def test_rejects_negative_total_volume(self) -> None:
        with pytest.raises(ValueError, match="total_volume_cm3"):
            _make_dvh_result(total_volume_cm3=-1.0)

    def test_rejects_negative_voxel_count(self) -> None:
        with pytest.raises(ValueError, match="voxel_count"):
            _make_dvh_result(voxel_count=-1)

    def test_rejects_negative_bin_width(self) -> None:
        with pytest.raises(ValueError, match="bin_width_gy"):
            _make_dvh_result(bin_width_gy=-0.01)

    def test_rejects_bad_supersampling_factor_length(self) -> None:
        with pytest.raises(ValueError, match="supersampling_factor"):
            _make_dvh_result(supersampling_factor=(5, 5))  # type: ignore[arg-type]

    def test_rejects_non_positive_supersampling_factor(self) -> None:
        with pytest.raises(ValueError, match="supersampling_factor"):
            _make_dvh_result(supersampling_factor=(5, 0, 5))

    def test_rejects_empty_point_in_polygon_method(self) -> None:
        with pytest.raises(ValueError, match="point_in_polygon_method"):
            _make_dvh_result(point_in_polygon_method="")

    def test_rejects_empty_interslice_method(self) -> None:
        with pytest.raises(ValueError, match="interslice_method"):
            _make_dvh_result(interslice_method="")

    def test_rejects_empty_endcap_method(self) -> None:
        with pytest.raises(ValueError, match="endcap_method"):
            _make_dvh_result(endcap_method="")


class TestDVHResultImmutability:
    """Verify that DVH arrays are read-only but warnings list is mutable."""

    def test_dose_bins_array_is_not_writeable(self) -> None:
        result = _make_dvh_result()
        assert result.dose_bins_gy.flags.writeable is False

    def test_cumulative_volume_array_is_not_writeable(self) -> None:
        result = _make_dvh_result()
        assert result.cumulative_volume_cm3.flags.writeable is False

    def test_warnings_list_is_mutable(self) -> None:
        result = _make_dvh_result()
        result.warnings.append("new warning")
        assert "new warning" in result.warnings


class TestDVHResultOptionalFields:
    """Verify optional fields default correctly and accept values."""

    def test_optional_fields_default_to_none(self) -> None:
        result = _make_dvh_result()
        assert result.preset_name is None
        assert result.surface_min_dose_gy is None
        assert result.surface_max_dose_gy is None
        assert result.computation_time_s is None

    def test_optional_fields_accept_values(self) -> None:
        result = _make_dvh_result(
            preset_name="CLINICAL_QA",
            surface_min_dose_gy=0.5,
            surface_max_dose_gy=2.1,
            computation_time_s=1.23,
            warnings=["test warning"],
        )
        assert result.preset_name == "CLINICAL_QA"
        assert result.surface_min_dose_gy == pytest.approx(0.5)
        assert result.surface_max_dose_gy == pytest.approx(2.1)
        assert result.computation_time_s == pytest.approx(1.23)
        assert result.warnings == ["test warning"]
