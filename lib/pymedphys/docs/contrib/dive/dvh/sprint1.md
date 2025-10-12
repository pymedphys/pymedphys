# Sprint 1 — DICOM I/O, Geometry & Structure Inspection

**Audience:** medical physicists & developers commissioning PyMedPhys’ DVH engine.

**Goal:** implement robust DICOM I/O, right‑prism voxelisation with explicit end‑caps, in‑slice polygon inclusion (with holes), and an inspect workflow that reports volume & slice‑spacing with evidence‑based warnings — all integrated into the existing PyMedPhys CLI as `pymedphys dvh …`.

## 1) What’s new in Sprint 1 (compared with Sprint 0)

- **DICOM I/O & frame reconciliation**

  - RTDOSE → `DoseGrid` (Gy; IPP/IOP; PixelSpacing; GridFrameOffsetVector; scaling).

  - RTSTRUCT → `Structure3D` (rings with holes, deduped z‑planes, sorted).

  - Optional CT geometry (slice positions/orientation) for consistency checks.

  - Best‑effort `FrameOfReferenceUID` linkage.

- **In‑slice inclusion** (`inclusion.py`)

  - Vectorised even–odd point‑in‑polygon with holes.

- **End‑cap policies** (`endcaps.py`)

  - `truncate` and `half_slice` (using *local* half‑distances; single‑slice fallback).

- **Right‑prism voxelisation** (`geometry.py`)

  - Fill per slab with the lower plane’s polygon; apply end‑caps.

  - `mask_volume_cc()` respects per‑slice non‑uniform dz from dose frames.

- **Structure inspection** (`api.inspect_structure`)

  - Returns volume (cc), slice count, min/median/max z‑spacing, applied policies.

  - Emits warnings: `≤ 7` slices, `< 1 cc`, and `> 0.2 mm` variation in z‑spacing.

- **CLI integration** (no separate binary):
  - `pymedphys dvh inspect-struct …` now runs the inspection end‑to‑end within the standard PyMedPhys command layout (same parser wiring pattern as `pymedphys dicom …`).

Why this matters: DVH differences across systems often stem from end‑caps, inter‑slice handling, and sampling; small‑volume/SRS cases are particularly sensitive. Making these choices explicit and auditable is essential for reproducible comparisons and reliable commissioning.

## 2) Files & modules added/updated

```graphql
pymedphys/_dvh/
  types.py        # DoseGrid, Structure3D, StructureContour, ImageVolume
  dicom_io.py     # RTDOSE/RTSTRUCT loaders (+ CT optional) + FOR checks & warnings
  inclusion.py    # even–odd polygon inclusion with holes (vectorised)
  endcaps.py      # truncate | half_slice → z-intervals per plane
  geometry.py     # right-prism voxeliser + mask_volume_cc()
  api.py          # inspect_structure() – reports stats & emits warnings
pymedphys/cli/
  dvh.py          # dvh presets | config | audit | inspect-struct
  __init__.py     # top-level parser integrates `dvh_cli(subparsers)`  :contentReference[oaicite:7]{index=7}
```

(The CLI registration follows the same subparser style used by the DICOM toolbox.)

## 3) Using it — CLI

### 3.1 Inspect a structure (right‑prism + end‑caps)

```bash
pymedphys dvh inspect-struct \
  --rtstruct RS.dcm \
  --rtdose RD.dcm \
  --structure "PTV_24" \
  --endcaps half_slice \
  --json-out artefacts/ptv24_inspect.json
```

**Stdout prints:** structure name, end‑caps, inclusion rule, slice count, min/median/max z‑spacing, volume (cc).

**Warnings** (stderr):

- Few slices (≤ 7) — DVH variability expected, especially in SRS‑sized ROIs.

- Small volume (< 1 cc) — DVH metrics (e.g., D95, near‑max) can shift materially.

- Non‑uniform z‑spacing (> 0.2 mm variation) — precision risk.

These advisories reflect current evidence for DVH uncertainty in small and sparsely sampled structures.

### 3.2 Other DVH CLI commands (from Sprint 0)

```bash
pymedphys dvh presets [--show NAME]
pymedphys dvh config  --preset NAME [--override KEY=VALUE ...]
pymedphys dvh audit   --preset NAME --out audit.json [INPUTS...]
```

The audit JSON continues to capture versions, Git state, input hashes, and the effective `DVHConfig`. (CLI integration mirrors existing PyMedPhys patterns. )

## 4) Using it — Python API

```python
from pymedphys._dvh.dicom_io import load_study
from pymedphys._dvh.api import inspect_structure

study = load_study(rtstruct="RS.dcm", rtdose="RD.dcm", ct_slices=None,
                   include_names=["PTV_24"])
info = inspect_structure(
    dose=study.dose,
    struct=study.structures["PTV_24"],
    endcaps="half_slice",            # or "truncate"
    inclusion_rule="even_odd",       # winding reserved for parity checks
)
print(info["volume_cc"], info["z_spacing_mm"])
```

## 5) Sanity checks & warnings (what’s enforced)

- Frame reconciliation: IPP/IOP/PixelSpacing/GridFrameOffsetVector parsed; `DoseGrid` exposes index↔world transforms; structures sorted & deduped per‑plane; optional CT geometry used for context.

- Spacing variability: if local inter‑slice spacings vary by > 0.2 mm → WARNING.

- Few slices: if plane count ≤ 7 → WARNING.

- Small volume: if voxelised volume < 1 cc → WARNING.

These conditions correspond to failure modes and heightened DVH variability identified in the literature and will help reviewers apply appropriate tolerances.

## 6) How we voxelise (design choices)

- **Inter‑slice rule:** right‑prism — a slab `[zk, zk+1)` uses the lower plane’s polygon; end‑caps extend at tips (policy‑controlled).

- **End‑caps:**

  - `truncate`: no extension beyond first/last planes (except an exact‑on‑plane slice gets the 2‑D mask so commissioning “area” checks behave sensibly).

  - `half_slice`: extend inferior/superior by half the local spacing (asymmetric when spacings differ).

- **In‑slice inclusion:** even–odd, supports holes; vectorised over the (Y,X) lattice.

- **Volume:** `mask_volume_cc()` uses mid‑plane distances between dose frames to compute per‑slice thickness — correct for non‑uniform `dz`.

This combination reproduces the conservative behaviour many TPSs approximate; shape‑based inter‑slice/end‑caps land in Sprint 2. The explicit policy avoids the “expand volume but exclude cap dose” inconsistency that has been observed historically.

## 7) Testing (what guards the behaviour)

### Unit tests (selected)

- Inclusion with holes: nested squares → raster area ≈ analytic within a voxel.

- End‑caps: half‑slice adds exactly the expected `πr² × half_mm × 2` (disc test); truncate adds none.

- Non‑uniform spacing: `Δz = [1.0, 2.0] mm` → half‑caps of `0.5` and `1.0` mm at ends.

- Right‑prism: between `z0` and `z1`, all voxels use the lower polygon; no leakage above `z1`.

### Integration tests

- Frame recon: a cube ROI offset from dose origin aligns in index↔world, and voxel areas match expected lattice counts.

- Small‑volume warnings: a ~`0.3 cc` “sphere” with `1 mm` spacing triggers `≤ 7` slices and `< 1 cc` warnings.

- CLI: the real top‑level parser is used (`define_parser()`), exercising `pymedphys dvh presets|config|audit|inspect-struct` without shelling out.

## 8) Known limitations (to be addressed in Sprint 2)

- Orientation generality: current path assumes standard axial alignment when building `(X,Y)` meshes; full arbitrary IOP handling is coming.

- Shape‑based inter‑slice & rounded end‑caps: reduces stair‑step artefacts for small structures and steep SI gradients.

- DVH curves & metrics: calculation, binning controls, and near‑min/near‑max metrics (e.g., `D0.03 cc`) land next; audits will then include DVH results.

## 9) CLI command reference (DVH, current)

```bash
pymedphys dvh presets [--show NAME]
pymedphys dvh config --preset NAME [--override KEY=VALUE ...]
pymedphys dvh audit --preset NAME --out PATH [INPUTS ...]
pymedphys dvh inspect-struct --rtstruct RS.dcm --rtdose RD.dcm --structure NAME
                             [--ct CT_DIR]
                             [--endcaps {truncate,half_slice}]
                             [--inclusion {even_odd,winding}]
                             [--single-slice-half-mm MM]
                             [--json-out PATH] [--quiet]
```

The DVH CLI is registered into PyMedPhys’ top‑level parser, following the existing CLI architecture.

## 10) Acceptance criteria (Sprint 1 — done)

- [x] RTDOSE/RTSTRUCT load; optional CT geometry parsed.

- [x] Structures voxelise to a 3D boolean mask aligned to the dose grid.

- [x] End‑cap policies (truncate, half_slice) implemented; behaviour verified on synthetic cases.

- [x] Right‑prism slabs pick the lower plane polygon; exact‑on‑plane assignment under truncate.

- [x] Warnings: non‑uniform spacing (> 0.2 mm), ≤ 7 slices, < 1 cc volume.

- [x] CLI inspect-struct integrated under pymedphys dvh ….

- [x] Unit & integration tests green across supported OS/Python.

## 11) References (motivation & design)

- Project plan & presets/validation roadmap — PyMedPhys DVH plan.

- Analytical ground truth & failure modes (end‑caps, sampling, surface probing) — Nelms et al., 2015.

- Multicentre differences & DVH‑gamma — Ebert et al., Comparison of DVH data from multiple TPSs.

- Clinical impact of DVH uncertainty, especially sub‑cc — Walker & Byrne.

- CLI integration pattern — PyMedPhys top‑level CLI & DICOM toolbox.

------------------------------------------

## Final word

Sprint 1 establishes the geometry bedrock on which DVH accuracy depends. We now have a transparent, testable path from DICOM to a volume‑correct 3D mask, with explicit policies and practical warnings. That’s the right springboard for Sprint 2: shape‑based inter‑slice handling, DVH computation & metrics, and precision characterisation — all emitted with the audit trail established in Sprint 0.
