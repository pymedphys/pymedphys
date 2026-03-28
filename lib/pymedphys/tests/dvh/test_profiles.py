"""Tests for DVHConfig named profiles (RFC section 6.6)."""

from __future__ import annotations

from pymedphys._dvh._types._config import (
    DVHConfig,
    DVHType,
    EndCapPolicy,
    InterpolationMethod,
    PointInPolygonRule,
)


class TestDVHConfigProfiles:
    """Verify the named configuration profiles return expected settings."""

    def test_reference_uses_shape_based(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.SHAPE_BASED

    def test_reference_uses_rounded_endcap(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.algorithm.endcap_policy == EndCapPolicy.ROUNDED

    def test_reference_uses_winding_number(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.WINDING_NUMBER

    def test_reference_uses_adaptive_supersampling(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.algorithm.supersampling.is_adaptive

    def test_reference_single_threaded(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.runtime.max_threads == 1

    def test_fast_uses_right_prism(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.RIGHT_PRISM

    def test_fast_uses_half_slice_endcap(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.endcap_policy == EndCapPolicy.HALF_SLICE

    def test_fast_uses_scanline_even_odd(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.SCANLINE_EVEN_ODD

    def test_fast_uses_fixed_supersampling(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.supersampling.factor == 3

    def test_fast_cumulative_only(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.dvh_type == DVHType.CUMULATIVE

    def test_default_construction_practical(self) -> None:
        cfg = DVHConfig()
        assert cfg.algorithm.dvh_bin_width_gy == 0.01
        assert cfg.runtime.deterministic is True
