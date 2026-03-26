# PyMedPhys DVH Subpackage: MVP-first Technical Design and Validation Plan

**Version:** 2.0
**Date:** 2026-03-22
**Author:** Matthew Jennings
**Target repository:** `pymedphys/pymedphys`
**Target package root:** `lib/pymedphys`
**License:** Apache-2.0
**Repository baseline:** follow the current upstream repository layout, supported Python range, developer workflow, and type-checking tooling.

---

## 1. Executive summary

This document defines an MVP-first plan for a robust dose-volume histogram (DVH) engine in PyMedPhys. The immediate goal is to solve the core needs behind PyMedPhys issue #1874:

- accurate 3D supersampling;
- clinically defensible structure interpolation and end-capping;
- accurate `Dmin` and `Dmax` through explicit surface dose sampling;
- a clean public API;
- and validation against analytical truth.

The plan deliberately narrows the first merge to a landable, reviewable core:

- **In scope for the initial PR:** external-beam style RTSTRUCT + RTDOSE workflows, axial patient-aligned DICOM, uniformly spaced rectilinear dose axes, binary voxel weighting, right-prism inter-slice interpolation, half-slab / capped / no-endcap strategies, surface min/max sampling, CSV/JSON export, a public API, a minimal CLI, and a strong validation suite.
- **Explicitly out of scope for the initial PR:** full TPS-emulation feature parity, oblique DICOM geometry, irregular-grid dose interpolation backends, partial-volume weighting, shape-based interpolation and tapering, DICOM RT DVH export, Streamlit GUI, and biological models.

That scope split is intentional. The first PR should land a trustworthy engine before it grows into a full research platform.

---

## 2. Repository and integration assumptions

The plan is aligned to the current PyMedPhys repository.

### 2.1 Code locations

New code should live under the current source tree:

```text
lib/pymedphys/_dvh/
lib/pymedphys/dvh.py
lib/pymedphys/cli/
lib/pymedphys/tests/dvh/
```

Do **not** create a parallel top-level `pymedphys/` package tree.

### 2.2 Tooling

Use the repository’s existing conventions:

- `uv` for environment management;
- repository development sync, not ad-hoc `pip install --break-system-packages`;
- `pyright`, not a new `mypy` workflow, unless the upstream repository later adopts `mypy`;
- local development on the repository’s currently supported Python range, with Python 3.12 preferred for day-to-day work if desired.

### 2.3 Initial PR philosophy

The first PR should be:

- additive;
- easy to review;
- clinically meaningful without being feature-complete;
- and conservative about silent fall-backs.

Where the engine cannot yet support a dataset safely, it should **raise a clear error or emit a prominent warning**, not silently reshape or reinterpret the data.

---

## 3. Scope boundary

### 3.1 Stage 1 - MVP

1. Core data types and public API surface.
2. Binary contour-to-volume voxelisation on a cropped supersampled grid.
3. Right-prism inter-slice interpolation.
4. End-capping:
   - `half_slab`
   - `capped_half_slab`
   - `no_endcap`
5. Surface dose sampling for exact-geometry `Dmin` and `Dmax`.
6. DICOM RT Structure Set and RT Dose parsing for **axial, patient-aligned, uniformly spaced rectilinear** datasets.
7. DVH statistics:
   - `Dmean`, `Dmin`, `Dmax`
   - `Dx%`, `Dcc`
   - `VxGy`, `Vx%`
   - `D0.03cc`
8. Validation:
   - Nelms analytical truth tests;
   - Pepin-inspired precision / stair-step behaviour analysis;
   - Ebert-style imported-DVH comparison hooks;
   - small-volume warnings informed by Walker & Byrne;
   - one explicit high-gradient edge-case regression.
9. Minimal JSON and CSV export.
10. Minimal CLI and public Python API.

### 3.2 Stage 2 - Comprehensive tool

These are worthwhile, but should be follow-up PRs unless the MVP lands unusually cleanly:

1. `ray_casting` PIP backend.
2. Shape-based interpolation.
3. Shape-based tapered end-caps.
4. Partial-volume voxel weighting.
5. Full 32-way strategy sweeps as standard CI.
6. DICOM RT DVH export.
7. Streamlit GUI.
8. Biological models (`EUD`, `TCP`, `NTCP`).
9. Oblique RT Dose / RT Structure support.
10. Irregular-axis fast interpolation backend.
11. Full Cutanda-style DeVH / uncertainty propagation implementation.

### 3.3 Scope statement for clinical claims

The MVP should **not** claim “general radiotherapy DVH support” without qualification.

It should instead state:

> Supports axial, patient-aligned RTSTRUCT/RTDOSE workflows on uniformly spaced rectilinear dose grids. Intended first for external-beam style use cases. High-gradient close-source brachytherapy and oblique / irregular-grid datasets are not yet full-production paths.

That narrower claim is honest and makes the validation story stronger.

---

## 4. Coordinate-system and DICOM contract

This is the most important correctness section.

### 4.1 External coordinate truth

All DICOM I/O should use the **DICOM Patient-Based Coordinate System** as the external truth:

- `x`: patient left is positive;
- `y`: patient posterior is positive;
- `z`: patient superior (head) is positive.

Do **not** describe this as “IEC 1217 as used by DICOM”. The DICOM patient frame is the correct I/O contract.

### 4.2 Internal array convention

Use:

```python
DoseGrid.axes = (x_mm, y_mm, z_mm)
DoseGrid.values.shape == (nx, ny, nz)
values[ix, iy, iz] corresponds to (x[ix], y[iy], z[iz])
```

Document clearly:

- this is an **axis-index contract**, not a statement about memory contiguity;
- in NumPy C-order, the **last index** is contiguous in memory.

### 4.3 Validation directions

To avoid DICOM/IEC confusion, the analytical and validation helpers should use **physical direction names**, not overloaded axis letters:

- `direction="AP"` means gradient along patient `y`;
- `direction="SI"` means gradient along patient `z`.

If any internal analytical helper wants axis letters, the mapping must be explicit and local to the validation module.

### 4.4 DICOM RT Dose parsing contract

For the MVP:

1. Accept **axial, patient-aligned** RT Dose only.
2. Parse `ImagePositionPatient`, `ImageOrientationPatient`, `PixelSpacing`, and `GridFrameOffsetVector`.
3. Detect non-axial or rotated orientations and raise an informative error.
4. Parse `pixel_array` from DICOM, then transpose from the unpacked RT Dose shape to the internal `(nx, ny, nz)` convention.
5. Apply `DoseGridScaling`.
6. Verify the gradient direction with an **asymmetric test case**.

### 4.5 RT Structure contract

For the MVP:

1. Accept planar contours only.
2. Reject unsupported contour types such as `OPEN_NONPLANAR` with a clear error.
3. Preserve per-contour geometric type metadata.
4. Sort contours by slice coordinate after parsing.
5. Keep enough metadata to decide slice-combination semantics correctly.

---

## 5. Contour semantics and edge conventions

### 5.1 Boundary inclusion

Boundary points are **inside** the structure.

This is an explicit project rule, not something delegated to Matplotlib. Matplotlib may still be used as a rough cross-check away from boundaries, but not as the authoritative oracle for boundary behaviour.

### 5.2 Multi-contour semantics

Do **not** hard-code “all multi-contour slices are XOR”.

Use this standards-aware rule set:

1. If an ROI is encoded with `CLOSEDPLANAR_XOR`, treat same-slice contours using XOR semantics.
2. If an ROI is encoded with `CLOSED_PLANAR`, do **not** assume XOR. Same-slice contours default to slice-wise union unless the file or caller explicitly indicates otherwise.
3. Keyhole hole encoding is valid under `CLOSED_PLANAR`; it should be handled by the contour geometry itself rather than by an XOR assumption.
4. Provide an **explicit vendor-compatibility mode** for non-conformant files, with a warning recorded in the result metadata.

### 5.3 Slab ownership

For right-prism interpolation, use half-open ownership:

```text
[z_lower, z_upper)
```

Grid points exactly on a midpoint belong to the lower slab.

### 5.4 End-cap dose inclusion

If the chosen end-cap strategy extends the structure, **dose in the extension must be included** in the DVH.

This is a permanent regression requirement because the Pinnacle inconsistency documented by Nelms arose specifically from extending volume without including extension-region dose.

---

## 6. Core data model

A minimal but sufficient data model for the initial PR is:

```python
@dataclass(frozen=True)
class PlanarContour:
    z_mm: float
    points_xy_mm: np.ndarray
    geometric_type: str = "CLOSED_PLANAR"

@dataclass(frozen=True)
class Structure:
    name: str
    number: int
    contours: tuple[PlanarContour, ...]
    colour_rgb: tuple[int, int, int] | None = None
    combination_mode: str = "auto"   # auto, xor, slice_union, vendor_compat_xor
    coordinate_frame: str = "DICOM_PATIENT"

@dataclass(frozen=True)
class DoseGrid:
    axes_mm: tuple[np.ndarray, np.ndarray, np.ndarray]   # x, y, z
    values_gy: np.ndarray                                # (nx, ny, nz)

@dataclass
class DVHResult:
    structure_name: str
    dose_bins_gy: np.ndarray
    cumulative_volume_cm3: np.ndarray
    total_volume_cm3: float
    voxel_count: int
    bin_width_gy: float
    preset_name: str | None
    supersampling_factor: tuple[int, int, int]
    pip_method: str
    interslice_method: str
    endcap_method: str
    warnings: list[str]
    surface_min_dose_gy: float | None = None
    surface_max_dose_gy: float | None = None
    computation_time_s: float | None = None
```

### 6.1 Bin semantics

Be explicit:

- `dose_bins_gy[i]` is a dose threshold;
- `cumulative_volume_cm3[i]` is the volume receiving at least that dose;
- both arrays may have the same length if they are stored as sampled cumulative curve points rather than histogram-bin edges.

Document this once in `DVHResult` and keep every downstream function consistent with it.

---

## 7. Algorithm design

### 7.1 Point-in-polygon

**MVP default:** winding number with explicit inclusive-boundary handling.

Reason:

- robust for concave polygons;
- easy to make deterministic;
- fits the slice-wise binary mask workflow.

**Post-MVP extension:** ray-casting backend for research comparison.

### 7.2 Inter-slice interpolation

**MVP default:** right-prism interpolation.

Reason:

- aligns with the most direct Nelms-style truth-comparison framework;
- is easier to test and reason about;
- is sufficient for the first merge.

**Post-MVP extension:** shape-based interpolation for Eclipse-style behaviour studies.

### 7.3 End-capping

**MVP:**

- `half_slab`
- `capped_half_slab` with default cap `1.5 mm`
- `no_endcap`

**Post-MVP:**

- shape-based taper.

### 7.4 Voxel weighting

**MVP:** binary in/out weighting.

**Post-MVP:** partial-volume weighting for boundary voxels.

This is a good extension, but it adds significant implementation and validation surface area and is not necessary to land the core engine.

### 7.5 Supersampling and memory safety

Supersampling must satisfy all of the following:

1. odd integer factors only;
2. original grid points preserved;
3. dose grid cropped to **structure bounding box + margin** before supersampling;
4. no whole-grid 5× supersampling on clinical datasets;
5. adaptive floor on voxels-in-bbox, not on whole-grid size.

The crop-before-supersample step is mandatory, not optional.

### 7.6 Irregular dose axes

For the initial PR, take the conservative path:

1. detect whether each axis is uniformly spaced to within a small tolerance;
2. if not, raise an informative error saying the fast MVP backend supports only uniformly spaced rectilinear dose grids;
3. do **not** silently resample the whole grid to minimum spacing.

**Post-MVP extension:** a separate slower irregular-grid backend.

### 7.7 Surface dose sampling

Surface dose sampling should be a first-class part of the core algorithm, not an optional afterthought.

Minimum MVP requirement:

- interpolate dose at contour vertices;
- use these samples to refine `Dmin` and `Dmax`.

Nice extension if easy:

- densify long contour edges before surface sampling so extremum estimates are not limited to the original contour vertex distribution.

### 7.8 Numba warm-up

Provide a small `warm_up()` helper in `_dvh.__init__` once the Numba kernels exist.

Use it to:

- compile the hot-path kernels before timing benchmarks;
- avoid charging first-call compilation time to the first scientific result in tests;
- keep warm-up explicit rather than hidden behind mysterious startup latency.

---

## 8. Clinical presets and warning policy

The engine should expose named presets rather than only raw numerical knobs.

### 8.1 Presets

Suggested starting presets:

```python
FAST_PREVIEW
  supersampling_factor=(3, 3, 3)
  bin_width_gy=0.05
  surface_sampling=True

CLINICAL_QA
  supersampling_factor=(5, 5, 5)
  bin_width_gy=0.01
  surface_sampling=True

SMALL_VOLUME
  supersampling_factor=(7, 7, 7)
  bin_width_gy=0.005
  surface_sampling=True

REFERENCE
  supersampling_factor=(9, 9, 9)
  bin_width_gy=0.001
  surface_sampling=True
```

Note that these are just *starting* presets, and are subject to change after suitable investigation of sensitivities of accuracy to each parameter.

### 8.2 Automatic warnings

Add human-readable warnings for at least:

- structure partly outside dose grid;
- non-axial DICOM orientation rejected;
- irregular dose axes unsupported in MVP;
- vendor-compatibility contour semantics assumed;
- very small structure volume;
- very low voxel count after voxelisation.

Suggested small-volume thresholds:

- `< 1 cc`: caution;
- `< 0.1 cc`: strong caution.

These are also subject to change post-sensitivity investigations.

The warning text should say that DVH metrics for very small volumes may show large uncertainty even when total volume appears reasonable.

---

## 9. DICOM I/O

### 9.1 Initial PR functions

1. `list_structure_names(rtstruct_ds) -> list[str]`
2. `structure_from_dicom(rtstruct_ds, roi_name) -> Structure`
3. `dose_grid_from_dicom(rtdose_ds) -> DoseGrid`

### 9.2 MVP support rules

Support:

- axial, patient-aligned RT Dose;
- monotonic, uniformly spaced axes;
- planar RTSTRUCT contours.

Detect and reject with clear messages:

- rotated / oblique dose orientation;
- unsupported contour types;
- irregular spacing outside the MVP tolerance.

### 9.3 Dose-grid coverage behaviour

If the structure extends beyond the dose grid:

- do not silently truncate without notice;
- either raise or, if clipping is allowed, clip with a prominent warning stored in `DVHResult.warnings`.

Default recommended behaviour for the initial PR:

- clip with warning for compute paths;
- provide a stricter option to raise.

---

## 10. Validation and benchmarking strategy

Validation should be layered.

### 10.1 Layer A: deterministic gating regression tests

These are small, fast, and run on every PR:

1. data-type invariants;
2. point-in-polygon correctness;
3. mask area / volume smoke tests;
4. supersample-grid invariants;
5. DICOM axis-ordering test with asymmetric dose field;
6. Pinnacle regression;
7. small-volume warning logic;
8. determinism / reproducibility;
9. one end-to-end Nelms sphere case.

These are pass/fail and should gate CI.

### 10.2 Layer B: analytical truth validation

Use analytical truth for:

- Nelms linear-gradient reference cases:
  - sphere;
  - axial cylinder;
  - rotated cylinder;
  - axial cone;
  - rotated cone.
- Walker & Byrne-style Gaussian sphere reference cases using numerical integration.

Record:

- `V`, `Dmean`, `Dmin`, `Dmax`, `D99`, `D95`, `D5`, `D1`, `D0.03cc`.

### 10.3 Layer C: continuous curve error reporting

Follow Nelms’ logic and compute **both**:

- volume error at sampled dose points;
- dose error at sampled volume points.

Do not report only one.

### 10.4 Layer D: precision / stair-step characterisation

Add Pepin-style spacing / resolution sweeps to show how the engine behaves as contours and dose grids coarsen. Include a dedicated Gaussian-dose tier so interpolation error at structure boundaries is tested directly rather than inferred only from linear-gradient cases.

### 10.5 Layer E: cross-system and imported-DVH comparison

Provide a framework to compare:

- TPS-exported DVHs;
- independently calculated DVHs;
- and, optionally, other open-source tools.

This is diagnostic, not truth.

### 10.6 Layer F: uncertainty-aware extension

Reserve a clean future slot for Cutanda-style uncertainty-aware DVH reporting, but keep it outside the initial PR.

### 10.7 High-gradient edge case

Because the MVP scope is narrowed to external-beam style workflows, one explicit close-gradient synthetic regression case is still worthwhile. A simple case is enough:

- small structure;
- steep gradient near a surface;
- strong sensitivity of near-maximum metric.

That gives a first guardrail without claiming brachytherapy-grade support.

---

## 11. Public API, CLI, and export

### 11.1 Public Python API

Initial PR should include a thin public re-export module:

```text
lib/pymedphys/dvh.py
```

Exports:

- `compute_dvh`
- `DoseGrid`
- `Structure`
- `PlanarContour`
- `DVHResult`
- statistics helpers
- DICOM I/O helpers
- JSON/CSV export helpers

### 11.2 CLI

Use the repository’s existing CLI style and parser approach.

Recommended initial command:

```text
pymedphys dvh compute
```

Support:

- RTSTRUCT path
- RTDOSE path
- structure name(s)
- preset
- optional overrides for supersampling / bin width
- JSON / CSV output

### 11.3 Export

**Initial PR:**

- JSON
- CSV

**Post-MVP:**

- DICOM RT DVH export

The DICOM RT DVH export path is useful, but it should not delay the core engine.

---

## 12. Package layout and roadmap

## 12.1 Initial PR package layout

```text
lib/pymedphys/
├── _dvh/
│   ├── __init__.py
│   ├── types.py
│   ├── presets.py
│   ├── _numba_kernels.py
│   ├── pip.py
│   ├── interslice.py
│   ├── endcap.py
│   ├── supersample.py
│   ├── voxelise.py
│   ├── histogram.py
│   ├── statistics.py
│   ├── analytical.py
│   ├── dicom_io.py
│   └── export.py
├── dvh.py
├── cli/
│   └── dvh.py
└── tests/
    └── dvh/
```

## 12.2 Phase roadmap

### Phase 0 — repository-aligned scaffold

- create module tree under `lib/pymedphys`;
- create tests under `lib/pymedphys/tests/dvh`;
- add `CLAUDE.md` aligned to upstream tooling and path conventions.

### Phase 1 — MVP core engine

- data types;
- presets;
- winding-number PIP;
- right-prism inter-slice interpolation;
- end-caps;
- supersampling;
- voxelisation;
- histogram;
- statistics.

### Phase 2 — clinical I/O and analytical validation

- DICOM RTSTRUCT / RTDOSE parsing;
- analytical functions;
- gating regression suite;
- non-gating validation reports.

### Phase 3 — public interface

- `pymedphys.dvh`;
- minimal CLI;
- JSON / CSV export.

### Phase 4 — research extensions

- ray-casting;
- shape-based interpolation;
- shape-based taper;
- partial-volume weighting;
- TPS-comparison utilities;
- D0.03cc versus Dmax stability study;
- close-gradient / brachy-like synthetic benchmarks;
- optional open-source comparison modules.

### Phase 5 — post-MVP interface and modelling extensions

- Streamlit GUI;
- DICOM RT DVH export;
- biological models;
- uncertainty-aware DVH / DeVH overlays;
- irregular-grid backend;
- oblique DICOM support.

---

## 13. CI and testing strategy

### 13.1 Gating CI

Gating CI should run only the compact deterministic subset.

### 13.2 Non-gating validation jobs

Full analytical validation, resolution sweeps, and strategy sweeps should run as:

- manual jobs;
- or artifact-producing validation jobs that do not block ordinary PRs.

### 13.3 Performance tests

Benchmark:

- 2D slice masking;
- 3D voxelisation;
- single-structure DVH on a representative cropped clinical grid.

Keep performance tests informative rather than brittle.

### 13.4 Determinism

Include an explicit reproducibility test so parallelism or reduction order does not introduce unstable outputs without notice.

### 13.5 Performance benchmarks

Keep a small non-gating benchmark suite that measures:

- 2D slice masking;
- 3D voxelisation on a cropped clinical-like bbox;
- one representative single-structure DVH calculation.

The point is to detect regressions, not to chase fragile absolute thresholds in ordinary CI.

---

## 14. TDD workflow

For each function or class:

1. write the test first;
2. confirm the test fails for the right reason;
3. implement the smallest correct solution;
4. run targeted tests;
5. run the full DVH test subset;
6. run `ruff`;
7. run `pyright`;
8. commit only when behaviour and typing are both clean.

For numerical kernels:

1. establish correctness in pure NumPy first where practical;
2. then add Numba;
3. then parallelise only if the result remains deterministic or the residual non-determinism is both tiny and documented.

---

## 15. Key implementation notes

1. Never silently reinterpret coordinate frames.
2. Never silently resample a whole irregular dose grid in the MVP.
3. Never assume all same-slice multi-contour data are XOR.
4. Never use Matplotlib boundary behaviour as the oracle for inclusion rules.
5. Never supersample the full clinical grid when a cropped structure bbox would do.
6. Never weaken regression tests.
7. Never claim broad clinical support outside the MVP scope boundary.

---

## 16. References to anchor the design

### Primary project papers

1. Nelms et al. 2015 — analytical truth and the Pinnacle inconsistency.
2. Pepin et al. 2022 — inter-system precision behaviour and parameter sweeps.
3. Walker & Byrne 2024 — clinical impact of small-volume DVH uncertainty.
4. Ebert et al. 2010 — independent-vs-exported DVH comparison in multi-system settings.
5. Cutanda & Vargas 2008 — uncertainty-aware DVH thinking.
6. Kirisits et al. 2007 — edge-slice and high-gradient DVH uncertainty, especially near sources.

### Additional standards / project anchors

7. PyMedPhys issue #1874.
8. DICOM patient-based coordinate system and ROI contour geometric types.
