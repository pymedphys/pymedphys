"""Tests for the benchmark case registry."""

from __future__ import annotations

import pytest

from pymedphys._dvh._benchmarks import (
    BENCHMARK_CASE_BY_ID,
    BENCHMARK_CASES,
    BenchmarkCase,
    verify_registry_consistency,
)
from pymedphys._dvh._benchmarks._geometry import mm3_to_cc


class TestBenchmarkCaseRegistry:
    """Tests for the named benchmark case registry."""

    def test_registry_is_non_empty(self) -> None:
        assert len(BENCHMARK_CASES) > 0

    def test_all_cases_have_unique_ids(self) -> None:
        ids = [c.case_id for c in BENCHMARK_CASES]
        assert len(ids) == len(set(ids))

    def test_lookup_by_id_works(self) -> None:
        case = BENCHMARK_CASE_BY_ID["sphere_r10"]
        assert case.shape == "sphere"
        assert case.parameters["radius_mm"] == 10.0

    def test_cc_consistent_with_mm3(self) -> None:
        for case in BENCHMARK_CASES:
            expected_cc = mm3_to_cc(case.expected_volume_mm3)
            assert case.expected_volume_cc == pytest.approx(
                expected_cc, rel=1e-12
            ), f"Case {case.case_id}: cc mismatch"

    def test_verify_registry_consistency_passes(self) -> None:
        """All registered cases must match their volume formulas."""
        verify_registry_consistency()

    def test_all_shapes_have_cases(self) -> None:
        shapes = {c.shape for c in BENCHMARK_CASES}
        expected_shapes = {
            "sphere",
            "cylinder",
            "cone",
            "ellipsoid",
            "torus",
            "cylindrical_shell",
            "rectangular_parallelepiped",
        }
        assert shapes == expected_shapes

    def test_case_is_frozen(self) -> None:
        case = BENCHMARK_CASES[0]
        with pytest.raises(AttributeError):
            case.case_id = "modified"  # type: ignore[misc]
