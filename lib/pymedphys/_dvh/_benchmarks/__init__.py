"""Analytical benchmark utilities for DVH validation.

Currently provides closed-form volume formulas for geometric primitives
(sphere, cylinder, cone, ellipsoid, torus, cylindrical shell,
rectangular parallelepiped) used in the Tier 1 analytical benchmark
suite. All inputs are in mm, all outputs are in mm³.

See RFC §8.1 and §9 (Phase 1) for design rationale.
"""

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
    "MM3_PER_CC",
    "cone_volume",
    "cylinder_volume",
    "cylindrical_shell_volume",
    "ellipsoid_volume",
    "mm3_to_cc",
    "rectangular_parallelepiped_volume",
    "sphere_volume",
    "torus_volume",
]
