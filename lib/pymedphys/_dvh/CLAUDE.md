# CLAUDE.md — DVH Module (`pymedphys._dvh`)

> **Scope:** This file supplements the repo-root `CLAUDE.md` with conventions specific to the DVH module. Where this file and the repo-root file conflict, **this file takes precedence** within `_dvh/` code. The repo-root file remains authoritative for all non-DVH work.

## Authoritative Design Document

All implementation decisions must be traceable to the [Technical RFC and Research Protocol](../docs/contrib/dive/dvh/PyMedPhys_DVH_RFC.md). The companion [Summaries of relevant DVH literature](../docs/contrib/dive/dvh/DVH_Literature_Summaries.md) provides the evidence base underpinning design choices.

**Module path:** `lib/pymedphys/_dvh/`

**Test path:** `lib/pymedphys/tests/dvh/`

---

## PyMedPhys-Specific Conventions (from repo-root CLAUDE.md)

These are inherited from the project root and apply here:

- **Package manager:** `uv` — use `uv sync --extra all --group dev` for development setup.
- **Linting/formatting:** `ruff check --fix .` and `ruff format .`
- **Type checking:** `pyright` (not mypy). Run via `uv run -- pyright`.
- **Test runner:** `uv run -- pymedphys dev tests tests/dvh/`
- **Docstring style:** NumPy style (not Google style).
- **Private/public module pattern:** Implementation in `_module/` directories; public API exposed through `__init__.py`.
- **Python version:** `>=3.10, <3.13` (per `pyproject.toml`).

---

## Python Version Implications

Since PyMedPhys supports Python 3.10+, `tomllib` (stdlib in 3.11+) is **not available on all supported versions**. The `MetricRequestSet.from_toml()` method must use a conditional import:

```python
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Fallback for 3.10
```

If `tomli` is not already in `pyproject.toml` dependencies, it should be added as a conditional dependency: `"tomli; python_version < '3.11'"`.

---

## Core Dependencies

| Package | Purpose | Notes |
| --- | --- | --- |
| `numpy>=1.26` | Array operations, core data types | Already in PyMedPhys |
| `numba` | JIT compilation, parallelisation | Already in PyMedPhys `[user]` and `[tests]` |
| `pydicom>=2.0.0` | DICOM RTSTRUCT/RTDOSE parsing | Already in PyMedPhys |
| `scipy` | `distance_transform_edt`, interpolation | Already in PyMedPhys |
| `hypothesis` | Property-based testing | Add to `[tests]` if not present |

**Do not add dependencies** beyond those already in PyMedPhys without explicit maintainer approval. Check `pyproject.toml` for what's available.

---

## Dataclass Conventions

All domain types use frozen dataclasses with slots:

```python
from __future__ import annotations
import numpy as np
import numpy.typing as npt
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)            # No arrays → default eq is fine
@dataclass(frozen=True, slots=True, eq=False)  # Has arrays → custom eq/hash
```

**Note on `Optional`:** Use modern `X | None` syntax (PEP 604) instead of `Optional[X]`. `from typing import Optional` is not needed.

**For types containing `np.ndarray`:**

1. Use `eq=False` on the dataclass
2. Defensively copy arrays in `__post_init__` and mark read-only
3. Implement `__eq__` using `np.array_equal`
4. Implement `__hash__` using `.tobytes()`

```python
def __post_init__(self) -> None:
    arr = np.array(self.my_array, dtype=np.float64)
    arr.flags.writeable = False
    object.__setattr__(self, 'my_array', arr)
```

**Cached derived properties on frozen dataclasses:**

`functools.cached_property` does not work with `slots=True` dataclasses because `slots=True` eliminates `__dict__`. **Rule:** For `slots=True` dataclasses, precompute derived values in `__post_init__` and store them as private fields, then expose via regular `@property`. Only use `cached_property` on classes that intentionally carry a `__dict__` (i.e., non-slots classes).

```python
@dataclass(frozen=True, slots=True)
class DVHBins:
    dose_bin_edges_gy: np.ndarray

    # Precompute derived values in __post_init__
    _cumulative_volume_cc: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # ... validation ...
        cumulative = np.cumsum(...)
        object.__setattr__(self, '_cumulative_volume_cc', cumulative)

    @property
    def cumulative_volume_cc(self) -> np.ndarray:
        return self._cumulative_volume_cc
```

---

## Import Style

```python
# Standard library first
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

# Third party
import numpy as np
import numpy.typing as npt

# PyMedPhys internal (use relative imports within _dvh)
from ._grid_frame import GridFrame
from ._roi_ref import ROIRef
```

---

## Docstring Format

Use **NumPy style** docstrings (per PyMedPhys convention):

```python
def compute_dvh(
    inputs: DVHInputs,
    request: MetricRequestSet,
    config: DVHConfig | None = None,
) -> DVHResultSet:
    """Compute DVH and extract metrics.

    This is the single public entry point for DVH computation.

    Parameters
    ----------
    inputs : DVHInputs
        Dose and structure data (DICOM or arrays).
    request : MetricRequestSet
        Which metrics to compute for which ROIs.
    config : DVHConfig, optional
        Algorithm, runtime, and policy settings.
        Defaults to DVHConfig() (practical mode).

    Returns
    -------
    DVHResultSet
        Per-ROI results, DVH curves, diagnostics, and provenance.

    Raises
    ------
    InvalidContour
        If config.policy.invalid_roi_policy is STRICT and any ROI
        has invalid geometry.
    """
```

---

## Naming

- Types: `PascalCase` (e.g., `GridFrame`, `MetricSpec`, `DVHBins`, `SDFField`)
- Functions/methods: `snake_case` (e.g., `compute_dvh`, `from_dicom`)
- Private modules: `_prefixed` (e.g., `_grid_frame.py`, `_compute.py`)
- Constants: `UPPER_SNAKE_CASE`
- Enum members: `UPPER_SNAKE_CASE` (e.g., `InterpolationMethod.SHAPE_BASED`)

---

## Error Handling

- Validate invariants in `__post_init__`. Once constructed, an object is guaranteed valid.
- Use `ValueError` for invalid construction arguments.
- Use domain-specific exceptions for pipeline errors: `InvalidContour`, `IncompatibleGrids`, `ROINotFound`.
- Never silently swallow errors. Use the `Issue` system for warnings and diagnostics.
- One bad ROI must never corrupt results for other ROIs.

---

## Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `_types/` | All domain types. No computation logic. Sub-modules below. |
| `_types/_grid_frame.py` | `GridFrame` — 3D grid with affine transform |
| `_types/_dose_ref.py` | `DoseReference`, `DoseReferenceSet` |
| `_types/_roi_ref.py` | `ROIRef` — ROI identity + colour |
| `_types/_issues.py` | `IssueLevel`, `IssueCode`, `Issue` |
| `_types/_metrics.py` | `MetricSpec`, `MetricFamily`, enums, `ROIMetricRequest`, `MetricRequestSet` |
| `_types/_config.py` | All config enums, `SupersamplingConfig`, `AlgorithmConfig`, `RuntimeConfig`, `PipelinePolicy`, `DVHConfig` |
| `_types/_contour.py` | `Contour` (raw), `PlanarRegion`, `ContourROI` |
| `_types/_dose.py` | `DoseGrid` |
| `_types/_occupancy.py` | `OccupancyField` |
| `_types/_sdf.py` | `SDFField` |
| `_types/_results.py` | `DVHBins`, `MetricResult`, `ROIResult`, `DVHResultSet`, provenance types |
| `_types/_inputs.py` | `DVHInputs` |
| `_grammar.py` | `MetricSpec.parse()` implementation (lives on MetricSpec itself) |
| `_serialisation.py` | JSON/TOML round-trip for all types |
| `_protocols.py` | Strategy protocols: `StructureModelBuilder`, `OccupancyComputer`, `DoseInterpolator` (private) |
| `_geometry/` | Point-in-polygon, SDF, contour interpolation, end-capping |
| `_occupancy/` | Voxelisation, supersampling, fractional occupancy |
| `_dose/` | Dose interpolation, surface-point sampling |
| `_histogram.py` | DVHBins construction from (dose, weight) pairs |
| `_metrics.py` | Metric extraction from DVHBins |
| `_io/` | DICOM RTSTRUCT/RTDOSE import, RTDOSE DVH export |
| `_compute.py` | `compute_dvh()` orchestrator |
| `_pipeline.py` | End-to-end DICOM pipeline |
| `_benchmarks/` | Analytical geometry, dose fields, DVH formulas, DICOM generation |
| `_cli.py` | CLI entry points |

## Design Decisions (Phase 0)

### ROIRef enrichment

`ROIRef` carries `colour_rgb` in addition to `name` and `roi_number`. This was added to the RFC specification because:

- Colour is DICOM ROI identity metadata (tag 3006,002A), not just display data
- It needs to travel through the pipeline to results for DVH plotting
- Without it, downstream code would need to look up the original structure data just to get the display colour

### ContourROI carries geometry-interpretation fields

`ContourROI` carries `combination_mode` and `coordinate_frame` (previously on a flat `Structure` type). These live on ContourROI rather than ROIRef because they govern how contours are combined during voxelisation, which is a geometry concern.

### `cached_property` incompatibility with `slots=True`

`functools.cached_property` does not work with `slots=True` dataclasses (no `__dict__`). For `DVHBins`, cumulative values are computed in `__post_init__` and stored as private `_cumulative_*` fields, exposed via regular `@property`.

### Development workflow: TDD

All development follows test-driven development: write tests first (Red), implement to pass (Green), refactor. Tests import from final module paths and are written before any implementation code.

---

## Key Design Invariants

These are non-negotiable constraints. Violating any of them is a bug.

1. **The Pinnacle Constraint:** The occupancy field used for volume computation and dose sampling must be the *same* `OccupancyField` instance. End-capped regions must be included in dose tallies. Named after the Nelms et al. [14] finding that Pinnacle v9.8 included end-cap volume but excluded end-cap dose voxels, causing Dmin errors up to 60%.

2. **Immutability:** All domain objects are frozen dataclasses. Mutation happens via `dataclasses.replace()`.

3. **Determinism:** When `RuntimeConfig.deterministic=True`, identical inputs + config produce bit-identical outputs. This requires fixed accumulation order and per-thread histogram buffers with a final reduction step (see `numba` thread-safety below).

4. **ROI isolation:** One bad ROI never silently corrupts results for other ROIs.

5. **Self-describing results:** Every `MetricResult` carries its `MetricSpec`. Every `ROIResult` carries its `ROIRef` and explicit status.

6. **No guessing dose references:** Any metric requiring a dose reference must have one explicitly supplied. The tool never infers or defaults a prescription dose.

---

## `numba` Thread-Safety

`numba.prange` with `nogil=True` and shared mutable accumulation buffers (e.g., histogram bins) requires careful design:

- Use **per-thread accumulation buffers** with a **final reduction step** rather than atomic writes to a shared buffer.
- When `RuntimeConfig.deterministic=True`, verify determinism by comparing single-threaded and multi-threaded outputs bit-for-bit.
- All parallel accumulation paths must be gated with explicit `deterministic` flag checks.
- Use Kahan (compensated) summation for all histogram accumulation.

---

## Array Axis Convention

**All 3D arrays use (z, y, x) axis order** — matching DICOM convention where z (slice direction) is the slowest-varying index. This is enforced by `GridFrame.shape_zyx`.

## Coordinate Convention

Patient coordinates in mm: (x, y, z) with x = patient left, y = patient posterior, z = patient superior (for HFS). The `GridFrame.index_to_patient_mm` affine maps (iz, iy, ix) → (x, y, z).

---

## Testing

### Organisation

```plaintext
lib/pymedphys/tests/dvh/
    conftest.py              # Shared fixtures
    test_types/
        test_grid_frame.py
        test_dose_ref.py
        test_roi_ref.py
        test_metrics.py      # MetricSpec, grammar parsing
        test_config.py
        test_contour.py
        test_sdf.py          # SDFField
        test_results.py      # DVHBins, ROIResult, DVHResultSet
        test_issues.py
    test_grammar.py          # MetricSpec.parse() round-trips
    test_serialisation.py    # JSON/TOML round-trip
    test_profiles.py         # DVHConfig.reference(), .fast()
    test_benchmarks/         # Phase 1+
    test_geometry/           # Phase 2+
    test_compute.py          # Phase 3+
    test_io/                 # Phase 4+
    test_pipeline.py         # Phase 4+
```

### Test Naming

```python
def test_grid_frame_from_uniform_correct_affine() -> None: ...
def test_grid_frame_rejects_nonpositive_shape() -> None: ...
def test_metric_spec_parse_HI_does_not_require_dose_ref() -> None: ...
def test_dvh_bins_cumulative_is_monotonically_nonincreasing() -> None: ...
```

### Test-First Development

**Write the test before the implementation. See it fail. Implement. See it pass.** This is non-negotiable per the RFC development practices.

### Property-Based Testing

Use `hypothesis` for dataclass invariants, metric grammar round-trips, and numerical monotonicity/bound properties.

### Benchmark Tests

After Phase 3, every PR to core computation code must pass the full Tier 1 analytical benchmark suite. Mark slow benchmarks:

```python
@pytest.mark.slow
@pytest.mark.benchmark
def test_nelms_sphere_reference_mode() -> None: ...
```

---

## Git Workflow

### Conventional Commits

Format: `type(scope): description`

Types: `feat`, `fix`, `test`, `refactor`, `docs`, `perf`, `chore`

Scopes for DVH work: `dvh/types`, `dvh/grammar`, `dvh/geometry`, `dvh/sdf`, `dvh/occupancy`, `dvh/dose`, `dvh/histogram`, `dvh/metrics`, `dvh/io`, `dvh/pipeline`, `dvh/benchmarks`, `dvh/config`, `dvh/serialisation`, `dvh/provenance`

### Branch Strategy

One feature branch per task. Branch name: `dvh/{phase}-{task}-{brief-description}`

Examples:

```plaintext
dvh/p0-task01-module-skeleton
dvh/p0-task02-metric-grammar
dvh/p1-task01-analytical-geometry
```

### PR Size

Target <500 lines per PR. If a task naturally exceeds this, split it.
