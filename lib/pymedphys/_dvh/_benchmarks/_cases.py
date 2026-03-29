"""Named benchmark cases for analytical volume validation.

Each ``BenchmarkCase`` bundles a shape, its parameters, the expected
closed-form volume, and a tolerance policy. Tests reference these
canonical cases instead of re-stating expected values ad hoc.

See RFC §8.1.1, §8.1.2 for specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from pymedphys._dvh._benchmarks._geometry import (
    cone_volume,
    cylinder_volume,
    cylindrical_shell_volume,
    ellipsoid_volume,
    mm3_to_cc,
    rectangular_parallelepiped_volume,
    sphere_volume,
    torus_volume,
)


@dataclass(frozen=True)
class BenchmarkCase:
    """A named analytical benchmark case.

    Parameters
    ----------
    case_id : str
        Unique human-readable identifier.
    shape : str
        Shape name (e.g. "sphere", "cylinder").
    parameters : Mapping[str, float]
        Shape parameters in mm.
    expected_volume_mm3 : float
        Analytically computed volume in mm³.
    expected_volume_cc : float
        Same volume in cc (1 cc = 1000 mm³).
    tolerance_policy : str
        Description of acceptable tolerance for voxelised comparison.
    source_note : str
        Reference or provenance note.
    """

    case_id: str
    shape: str
    parameters: Mapping[str, float]
    expected_volume_mm3: float
    expected_volume_cc: float
    tolerance_policy: str
    source_note: str


def _make_case(
    case_id: str,
    shape: str,
    parameters: Mapping[str, float],
    volume_mm3: float,
    tolerance_policy: str = "rel=1e-9 for analytical, <1% for voxelised",
    source_note: str = "closed-form formula",
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        shape=shape,
        parameters=dict(parameters),
        expected_volume_mm3=volume_mm3,
        expected_volume_cc=mm3_to_cc(volume_mm3),
        tolerance_policy=tolerance_policy,
        source_note=source_note,
    )


# ── Canonical benchmark cases ──────────────────────────────────────

BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    _make_case(
        case_id="sphere_r10",
        shape="sphere",
        parameters={"radius_mm": 10.0},
        volume_mm3=sphere_volume(10.0),
        source_note="RFC §9 Task 1.1",
    ),
    _make_case(
        case_id="sphere_r1",
        shape="sphere",
        parameters={"radius_mm": 1.0},
        volume_mm3=sphere_volume(1.0),
        source_note="unit sphere: V = 4π/3",
    ),
    _make_case(
        case_id="cylinder_r12_h24",
        shape="cylinder",
        parameters={"radius_mm": 12.0, "height_mm": 24.0},
        volume_mm3=cylinder_volume(12.0, 24.0),
        source_note="Nelms et al. [14]",
    ),
    _make_case(
        case_id="cone_r12_h24",
        shape="cone",
        parameters={"radius_mm": 12.0, "height_mm": 24.0},
        volume_mm3=cone_volume(12.0, 24.0),
        source_note="Nelms et al. [14]",
    ),
    _make_case(
        case_id="ellipsoid_10_5_3",
        shape="ellipsoid",
        parameters={"semi_a_mm": 10.0, "semi_b_mm": 5.0, "semi_c_mm": 3.0},
        volume_mm3=ellipsoid_volume(10.0, 5.0, 3.0),
    ),
    _make_case(
        case_id="torus_R20_r5",
        shape="torus",
        parameters={"major_radius_mm": 20.0, "minor_radius_mm": 5.0},
        volume_mm3=torus_volume(20.0, 5.0),
    ),
    _make_case(
        case_id="shell_R11_r10_h20",
        shape="cylindrical_shell",
        parameters={
            "outer_radius_mm": 11.0,
            "inner_radius_mm": 10.0,
            "height_mm": 20.0,
        },
        volume_mm3=cylindrical_shell_volume(11.0, 10.0, 20.0),
    ),
    _make_case(
        case_id="box_10_10_10",
        shape="rectangular_parallelepiped",
        parameters={"length_mm": 10.0, "width_mm": 10.0, "height_mm": 10.0},
        volume_mm3=rectangular_parallelepiped_volume(10.0, 10.0, 10.0),
        source_note="10mm cube = 1000 mm³ = 1.0 cc",
    ),
)


# Lookup by case_id for convenience
BENCHMARK_CASE_BY_ID: Mapping[str, BenchmarkCase] = {
    c.case_id: c for c in BENCHMARK_CASES
}


# Shape → volume function mapping for verification
_SHAPE_VOLUME_FUNCTIONS = {
    "sphere": lambda p: sphere_volume(p["radius_mm"]),
    "cylinder": lambda p: cylinder_volume(p["radius_mm"], p["height_mm"]),
    "cone": lambda p: cone_volume(p["radius_mm"], p["height_mm"]),
    "ellipsoid": lambda p: ellipsoid_volume(
        p["semi_a_mm"], p["semi_b_mm"], p["semi_c_mm"]
    ),
    "torus": lambda p: torus_volume(p["major_radius_mm"], p["minor_radius_mm"]),
    "cylindrical_shell": lambda p: cylindrical_shell_volume(
        p["outer_radius_mm"], p["inner_radius_mm"], p["height_mm"]
    ),
    "rectangular_parallelepiped": lambda p: rectangular_parallelepiped_volume(
        p["length_mm"], p["width_mm"], p["height_mm"]
    ),
}


def verify_registry_consistency() -> None:
    """Verify that all registered cases match their volume formulas.

    Raises
    ------
    AssertionError
        If any case's expected volume doesn't match the formula output.
    """
    for case in BENCHMARK_CASES:
        fn = _SHAPE_VOLUME_FUNCTIONS[case.shape]
        computed = fn(case.parameters)
        assert np.isclose(computed, case.expected_volume_mm3, rtol=1e-12), (
            f"Case {case.case_id}: formula gives {computed} mm³ but "
            f"registry says {case.expected_volume_mm3} mm³"
        )
        assert np.isclose(mm3_to_cc(computed), case.expected_volume_cc, rtol=1e-12), (
            f"Case {case.case_id}: cc conversion mismatch"
        )
