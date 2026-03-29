"""Analytical benchmark utilities for DVH validation.

Currently provides closed-form volume formulas for geometric primitives
(sphere, cylinder, cone, ellipsoid, torus, cylindrical shell,
rectangular parallelepiped) used in the Tier 1 analytical benchmark
suite. All inputs are in mm, all outputs are in mm³.

Also provides a named benchmark-case registry for reusable ground-truth
validation.

See RFC §8.1 and §9 (Phase 1) for design rationale.
"""

from pymedphys._dvh._benchmarks._cases import (
    BENCHMARK_CASE_BY_ID,
    BENCHMARK_CASES,
    BenchmarkCase,
    verify_registry_consistency,
)
from pymedphys._dvh._benchmarks._geometry import (
    MM3_PER_CC,
    cone_volume,
    cylinder_volume,
    cylindrical_shell_volume,
    ellipsoid_volume,
    mm3_to_cc,
    rectangular_parallelepiped_volume,
    sphere_volume,
    torus_volume,
)

__all__ = [
    "BENCHMARK_CASES",
    "BENCHMARK_CASE_BY_ID",
    "BenchmarkCase",
    "MM3_PER_CC",
    "cone_volume",
    "cylinder_volume",
    "cylindrical_shell_volume",
    "ellipsoid_volume",
    "mm3_to_cc",
    "rectangular_parallelepiped_volume",
    "sphere_volume",
    "torus_volume",
    "verify_registry_consistency",
]
