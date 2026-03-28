"""Tests for DVHConfig named profiles (RFC section 6.6)."""

from __future__ import annotations

import warnings

import pytest

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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.reference()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.SHAPE_BASED

    def test_reference_uses_rounded_endcap(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.reference()
        assert cfg.algorithm.endcap_policy == EndCapPolicy.ROUNDED

    def test_reference_uses_winding_number(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.reference()
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.WINDING_NUMBER

    def test_reference_uses_adaptive_supersampling(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.reference()
        assert cfg.algorithm.supersampling.is_adaptive

    def test_reference_single_threaded(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.reference()
        assert cfg.runtime.max_threads == 1

    def test_fast_uses_right_prism(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.fast()
        assert cfg.algorithm.interpolation_method == InterpolationMethod.RIGHT_PRISM

    def test_fast_uses_half_slice_endcap(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.fast()
        assert cfg.algorithm.endcap_policy == EndCapPolicy.HALF_SLICE

    def test_fast_uses_scanline_even_odd(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.fast()
        assert cfg.algorithm.point_in_polygon == PointInPolygonRule.SCANLINE_EVEN_ODD

    def test_fast_uses_fixed_supersampling(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.fast()
        assert cfg.algorithm.supersampling.factor == 3

    def test_fast_cumulative_only(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cfg = DVHConfig.fast()
        assert cfg.algorithm.dvh_type == DVHType.CUMULATIVE

    def test_default_construction_practical(self) -> None:
        cfg = DVHConfig()
        assert cfg.algorithm.dvh_bin_width_gy == 0.01
        assert cfg.runtime.deterministic is True


class TestDVHConfigProfileWarnings:
    """Verify that TENTATIVE profiles emit UserWarning."""

    def test_reference_emits_user_warning(self) -> None:
        with pytest.warns(UserWarning, match="TENTATIVE"):
            DVHConfig.reference()

    def test_fast_emits_user_warning(self) -> None:
        with pytest.warns(UserWarning, match="TENTATIVE"):
            DVHConfig.fast()

    def test_reference_warning_mentions_phase_3(self) -> None:
        with pytest.warns(UserWarning, match="Phase 3"):
            DVHConfig.reference()

    def test_fast_warning_mentions_phase_3(self) -> None:
        with pytest.warns(UserWarning, match="Phase 3"):
            DVHConfig.fast()
