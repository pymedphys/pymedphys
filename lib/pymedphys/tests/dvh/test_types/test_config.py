"""Tests for configuration types (RFC section 6.6)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._config import (
    AlgorithmConfig,
    DoseInterpolationMethod,
    DVHConfig,
    DVHType,
    EndCapPolicy,
    FloatingPointPrecision,
    InterpolationMethod,
    InvalidROIPolicy,
    OccupancyMethod,
    PipelinePolicy,
    PointInPolygonRule,
    RuntimeConfig,
    SupersamplingConfig,
)


class TestEnums:
    """Verify all enum members exist."""

    def test_interpolation_method(self) -> None:
        assert InterpolationMethod.RIGHT_PRISM == "right_prism"
        assert InterpolationMethod.SHAPE_BASED == "shape_based"

    def test_endcap_policy(self) -> None:
        assert EndCapPolicy.NONE == "none"
        assert EndCapPolicy.HALF_SLICE == "half_slice"
        assert EndCapPolicy.HALF_SLICE_CAPPED == "half_slice_capped"
        assert EndCapPolicy.ROUNDED == "rounded"

    def test_occupancy_method(self) -> None:
        assert OccupancyMethod.BINARY_CENTRE == "binary_centre"
        assert OccupancyMethod.FRACTIONAL_SUPERSAMPLED == "fractional_supersampled"
        assert OccupancyMethod.ADAPTIVE_SUPERSAMPLED == "adaptive_supersampled"

    def test_point_in_polygon_rule(self) -> None:
        assert PointInPolygonRule.SCANLINE_EVEN_ODD == "scanline_even_odd"
        assert PointInPolygonRule.WINDING_NUMBER == "winding_number"

    def test_dose_interpolation_method(self) -> None:
        assert DoseInterpolationMethod.TRILINEAR == "trilinear"
        assert DoseInterpolationMethod.TRICUBIC_CATMULL_ROM == "tricubic_catmull_rom"
        assert DoseInterpolationMethod.TRICUBIC_BSPLINE == "tricubic_bspline"

    def test_dvh_type(self) -> None:
        assert DVHType.CUMULATIVE == "cumulative"
        assert DVHType.DIFFERENTIAL == "differential"
        assert DVHType.BOTH == "both"

    def test_invalid_roi_policy(self) -> None:
        assert InvalidROIPolicy.STRICT == "strict"
        assert InvalidROIPolicy.REPAIR_IF_SAFE == "repair_if_safe"
        assert InvalidROIPolicy.SKIP_INVALID == "skip_invalid"

    def test_floating_point_precision(self) -> None:
        assert FloatingPointPrecision.FLOAT32 == "float32"
        assert FloatingPointPrecision.FLOAT64 == "float64"


class TestSupersamplingConfig:
    def test_adaptive_sets_factor_none(self) -> None:
        cfg = SupersamplingConfig.adaptive()
        assert cfg.factor is None
        assert cfg.is_adaptive is True

    def test_fixed_sets_factor(self) -> None:
        cfg = SupersamplingConfig.fixed(3)
        assert cfg.factor == 3
        assert cfg.is_adaptive is False

    def test_rejects_factor_less_than_1(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            SupersamplingConfig(factor=0)

    def test_rejects_negative_min_voxels(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            SupersamplingConfig(adaptive_min_voxels=0)

    def test_rejects_nonpositive_convergence_tol(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            SupersamplingConfig(adaptive_convergence_tol=0.0)


class TestAlgorithmConfig:
    def test_default_construction(self) -> None:
        cfg = AlgorithmConfig()
        assert cfg.dvh_bin_width_gy == 0.01
        assert cfg.interpolation_method == InterpolationMethod.SHAPE_BASED

    def test_rejects_nonpositive_bin_width(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            AlgorithmConfig(dvh_bin_width_gy=0.0)

    def test_rejects_negative_bin_width(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            AlgorithmConfig(dvh_bin_width_gy=-0.01)

    def test_requires_endcap_max_mm_for_half_slice_capped(self) -> None:
        with pytest.raises(ValueError, match="endcap_max_mm"):
            AlgorithmConfig(endcap_policy=EndCapPolicy.HALF_SLICE_CAPPED)

    def test_accepts_half_slice_capped_with_max_mm(self) -> None:
        cfg = AlgorithmConfig(
            endcap_policy=EndCapPolicy.HALF_SLICE_CAPPED,
            endcap_max_mm=1.5,
        )
        assert cfg.endcap_max_mm == 1.5


class TestRuntimeConfig:
    def test_default_construction(self) -> None:
        cfg = RuntimeConfig()
        assert cfg.deterministic is True
        assert cfg.max_threads is None

    def test_rejects_nonpositive_batch_size(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            RuntimeConfig(batch_size_gb=0.0)

    def test_rejects_max_threads_less_than_1(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            RuntimeConfig(max_threads=0)


class TestPipelinePolicy:
    def test_default_construction(self) -> None:
        cfg = PipelinePolicy()
        assert cfg.invalid_roi_policy == InvalidROIPolicy.REPAIR_IF_SAFE
        assert cfg.anonymise_provenance is False
        assert cfg.z_tolerance_mm == 0.01


class TestDVHConfig:
    def test_default_construction(self) -> None:
        cfg = DVHConfig()
        assert isinstance(cfg.algorithm, AlgorithmConfig)
        assert isinstance(cfg.runtime, RuntimeConfig)
        assert isinstance(cfg.policy, PipelinePolicy)

    def test_reference_profile(self) -> None:
        cfg = DVHConfig.reference()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.SHAPE_BASED
        assert cfg.algorithm.endcap_policy == EndCapPolicy.ROUNDED
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.WINDING_NUMBER
        assert cfg.algorithm.supersampling.is_adaptive
        assert cfg.algorithm.surface_sampling is True
        assert cfg.algorithm.dvh_bin_width_gy == 0.005
        assert cfg.runtime.deterministic is True
        assert cfg.runtime.max_threads == 1

    def test_fast_profile(self) -> None:
        cfg = DVHConfig.fast()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.RIGHT_PRISM
        assert cfg.algorithm.endcap_policy == EndCapPolicy.HALF_SLICE
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.SCANLINE_EVEN_ODD
        assert cfg.algorithm.supersampling.factor == 3
        assert cfg.algorithm.surface_sampling is False
        assert cfg.algorithm.dvh_bin_width_gy == 0.01
        assert cfg.algorithm.dvh_type == DVHType.CUMULATIVE
