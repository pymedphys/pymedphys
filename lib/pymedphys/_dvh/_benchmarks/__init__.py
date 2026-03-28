"""Analytical benchmark utilities for DVH validation.

Provides analytical volume formulas, dose field generators, DVH formulas,
and DICOM test object generators for the Tier 1 benchmark suite.

See RFC §8.1 and §9 (Phase 1) for design rationale.
"""

from pymedphys._dvh._benchmarks._dose_fields import (
    linear_gradient_dose,
    radial_gaussian_dose,
)
from pymedphys._dvh._benchmarks._dvh_analytical import (
    cone_linear_gradient_dvh,
    cylinder_linear_gradient_dvh,
    sphere_linear_gradient_dvh,
    sphere_radial_gaussian_dvh,
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
    # Geometry (Task 1.1)
    "MM3_PER_CC",
    "cone_volume",
    "cylinder_volume",
    "cylindrical_shell_volume",
    "ellipsoid_volume",
    "mm3_to_cc",
    "rectangular_parallelepiped_volume",
    "sphere_volume",
    "torus_volume",
    # Dose fields (Task 1.2)
    "linear_gradient_dose",
    "radial_gaussian_dose",
    # Analytical DVH (Task 1.2)
    "cone_linear_gradient_dvh",
    "cylinder_linear_gradient_dvh",
    "sphere_linear_gradient_dvh",
    "sphere_radial_gaussian_dvh",
]
