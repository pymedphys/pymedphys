# Sprint 0 — DVH engine scaffold, configuration & audit

**Audience:** clinical medical physicists and developers working on PyMedPhys’ DVH engine.

**Goal:** ship a clean, testable scaffold that makes calculation choices explicit (via DVHConfig), records run provenance (via the audit JSON), and exposes both through the existing PyMedPhys CLI.

## 1) Scope & objectives (what Sprint 0 delivers)

### In scope

- A typed, serialisable DVHConfig with validation and presets for common use cases.

- A structured audit record (JSON) that captures config, versions, Git SHA (best‑effort), and cryptographic hashes of inputs.

- A CLI integrated into the main pymedphys command:

  - `pymedphys dvh presets`, `pymedphys dvh config`, `pymedphys dvh audit` (`compute` stays a stub).

- CI + local tooling: ruff, pytest, pre‑commit hooks and a 3‑OS/2‑Python matrix.

### Out of scope (deferred to Sprint 1+)

- DICOM geometry/voxelisation, end‑caps, inter‑slice rules, DVH curves/metrics.

- GPU/JIT acceleration paths.

The DVH CLI is integrated into the top‑level PyMedPhys parser and follows the same subparser wiring pattern as the existing DICOM toolbox, so users invoke it as `pymedphys dvh …` alongside other toolsets.

## 2) Repository layout (relevant bits)

```graphql
pymedphys/
  _dvh/
    __init__.py
    config.py        # DVHConfig + presets + validation
    audit.py         # AuditRecord + build_audit()
    dicom_io.py      # (largely Sprint 1; parses RTSTRUCT/RTDOSE etc.)
    inclusion.py     # (Sprint 1) in-slice polygon inclusion
    endcaps.py       # (Sprint 1) end-cap interval policies
    geometry.py      # (Sprint 1) right-prism voxelisation + volumes
    api.py           # inspect helpers (Sprint 1)
  cli/
    __init__.py      # top-level CLI parser + subparsers
    dvh.py           # DVH subcommands: presets/config/audit/inspect-struct
docs/
  contrib/
    dive/
      dvh/
        sprint0.md   # this document
tests/
  dvh/
    unit/ …          # TDD suites for config/audit/CLI
```

## 3) Configuration (DVHConfig) in brief

`DVHConfig` is a frozen dataclass that specifies *how* DVH will be computed.
It is fully serialisable (stable field order), validates internal consistency, and exposes presets via `DVHConfig.from_preset(name)`.

### Key fields (selected)

- Voxelisation / geometry choices (reserved for Sprint 1+): `interslice_interp`, `endcaps`, `inclusion_rule`.

- Sampling controls (future supersampling): `target_points`, `grid_factor`, `target_subvoxel_mm`.

- Dose interpolation: `interpolation` (`trilinear` default).

- Histogram binning: `bins_mode` (`dynamic`/`fixed`) + `min_bins`/`max_bins` or `bin_width_gy`.

- Extrema strategy: whether to probe surface vertices in addition to volume samples (later).

- Reproducibility/perf toggles: `deterministic`, `random_seed`, `gpu`, `jit`.

- Analysis flags: `precision_analysis` (write DVH‑precision indicators later).

### Presets

`clinical_qa`, `srs_small_volume`, `max_accuracy`, `fast_preview`.

#### Example

```bash
# Show a preset (JSON)
pymedphys dvh presets --show clinical_qa

# Resolve a preset + overrides (JSON)
pymedphys dvh config --preset clinical_qa \
  --override target_points=200000 \
  --override precision_analysis=false
```

## 4) Audit trail (what’s captured and why)

Every run writes a compact audit JSON next to outputs. It records:

- Identity & environment: timestamp (UTC), hostname, Python, OS/platform, package versions (`pymedphys`, `numpy`, `scipy`, `pydicom`), best‑effort Git SHA/branch/dirty.

- Inputs: paths (if applicable), SHA‑256 hashes, sizes; later, DICOM SOP/series UIDs.

- Config: the effective `DVHConfig` (including preset + overrides) as a JSON dict.

- Extras: CLI invocation and optional fields (reference dose, structure name, notes).

Rationale: DVH metrics can vary materially with algorithmic choices (end‑caps, inter‑slice handling, sampling/binning). Preserving the “recipe + context” makes comparisons reproducible and defendable.

Example creation:

```bash
pymedphys dvh audit --preset clinical_qa \
  --out artefacts/audit.json \
  RS.dcm RD.dcm CT/
```

```json
Snippet (trimmed):

{
  "timestamp_utc": "2025-10-11T08:24:39+00:00",
  "hostname": "physics-ws01",
  "python_version": "3.12.5",
  "package_versions": {"pymedphys": "x.y.z", "numpy": "2.0.1", "pydicom": "3.0.1"},
  "git": {"commit": "7b4f1c9", "branch": "main", "dirty": "false"},
  "config": {
    "preset": "clinical_qa",
    "endcaps": "shape_based",
    "bins_mode": "dynamic",
    "min_bins": 10000,
    "max_bins": 50000,
    "...": "..."
  },
  "inputs": [
    {"path": "RS.dcm", "size_bytes": 123456, "sha256": "…"},
    {"path": "RD.dcm", "size_bytes": 789012, "sha256": "…"}
  ],
  "extra": {"cli": {"subcommand": "audit", "preset": "clinical_qa", "argv": ["dvh","audit","..."]}}
}
```

## 5) CLI — integrated with the main PyMedPhys command

Sprint 0 exposes `presets`, `config`, and `audit` within the existing top‑level CLI:

```bash
# Help
pymedphys dvh --help
pymedphys dvh presets --help
pymedphys dvh config  --help
pymedphys dvh audit   --help
```

This mirrors how other PyMedPhys toolboxes are wired (e.g., `pymedphys dicom …`). The DVH CLI is registered by the top‑level parser and uses the same subparser + `set_defaults(func=...)` pattern as `pymedphys/cli/dicom.py`, so tooling and UX remain consistent.

> Heads‑up: A convenience `compute` command exists but is intentionally a stub in Sprint 0; it only writes an audit JSON. DVH curves and metrics arrive in Sprint 2+.

## 6) Quality gates & dev workflow

- Python: 3.12 & 3.13 across Windows/macOS/Linux.

- Style & types: `ruff` (lint/imports), `black` (format), `mypy` (typing if enabled).

- Tests: `pytest` unit + (later) integration tests.

- Hooks: `pre‑commit` runs ruff/black/misc fixers.

- CI: GitHub Actions matrix (3 OS × 2 Python); run lint → typecheck → unit. Coverage artifact uploaded.

Quick commands:

```bash
# Lint + format
uv run ruff check
uv run ruff format

# Unit tests
uv run pytest -q

# All hooks
uv run pre-commit run --all-files
```

## 7) Quick start (end‑to‑end)

### 1. Inspect presets & config

```bash
pymedphys dvh presets
pymedphys dvh presets --show srs_small_volume
pymedphys dvh config --preset clinical_qa --override target_points=150000
```

### 2. Create an audit for your inputs

```bash
pymedphys dvh audit --preset clinical_qa --out artefacts/audit.json RS.dcm RD.dcm CT/
```

### 3. (Optional preview of Sprint 1) Check structure geometry

```bash
pymedphys dvh inspect-struct \
  --rtstruct RS.dcm --rtdose RD.dcm --structure "PTV_66" \
  --endcaps half_slice --json-out artefacts/ptv66_inspect.json
```

> `inspect-struct` uses right‑prism inter‑slice handling and explicit end‑caps. It prints volume and z‑spacing stats and emits warnings for few‑slice and < 1 cc structures (feature lands during Sprint 1).

## 8) Testing the CLI (how we keep it reliable)

We test the DVH CLI without spawning a subprocess by using the same top‑level parser as the real `pymedphys` command and calling the registered subcommand functions with pytest. This is the same approach used across the PyMedPhys CLI stack.

Example (excerpt):

```python
from pymedphys.cli.__init__ import define_parser

def test_cli_presets(capsys):
    parser = define_parser()
    args = parser.parse_args(["dvh", "presets"])
    args.func(args)
    assert "Available DVH presets" in capsys.readouterr().out
```

## 9) Data governance & security

- The audit uses cryptographic hashes (SHA‑256) and SOP/series UIDs (in later sprints) to identify inputs without PHI.

- If audit files are exported outside your organisation, review the `inputs.path` values and redact if necessary.

## 10) Definition of Done — Sprint 0 (acceptance checklist)

- [x] Config: `DVHConfig` defined; presets implemented; validation enforced.

- [x] Audit: `AuditRecord` writes environment, versions, Git SHA (best‑effort), and input hashes.

- [x] CLI: `pymedphys dvh presets|config|audit` wired into the existing CLI and documented.

- [x] Tooling: ruff/pytest/pre‑commit in place; CI green across supported OS/Python.

- [x] Docs: this `sprint0.md` published and linked from the DVH index page.

## 11) What’s next (Sprint 1 preview)

- DICOM I/O & frame reconciliation (RTSTRUCT/RTDOSE/CT), right‑prism inter‑slice rule, and truncate/half‑slice end‑caps.

- Structure inspection via CLI (`inspect-struct`): volume, slice count, min/median/max z‑spacing and warnings for few‑slice/ < 1 cc.

- Unit/integration tests on synthetic datasets to lock in behaviour.

---------------------------------------------------

## Appendix A — DVH CLI command reference (Sprint 0)

```bash
pymedphys dvh presets [--show NAME]
    List presets or emit a preset as JSON.

pymedphys dvh config --preset NAME [--override K=V ...]
    Show a resolved configuration (JSON), with optional overrides.

pymedphys dvh audit --preset NAME --out PATH [INPUT ...]
    Write an audit JSON capturing config, versions and hashes for the given inputs.
```

> Tip: `--override` supports booleans, ints and floats:
> `--override precision_analysis=false --override target_points=150000`

## Appendix B — Minimal examples (copy‑paste)

```bash
# 1) Basic smoke
pymedphys dvh presets --show clinical_qa

# 2) Config with overrides (stdout JSON)
pymedphys dvh config --preset srs_small_volume --override min_bins=50000 --override max_bins=100000

# 3) Audit sidecar
mkdir -p artefacts
pymedphys dvh audit --preset clinical_qa --out artefacts/audit.json RS.dcm RD.dcm
```

-------------------------------------------------;

*This sprint aligns the DVH effort with PyMedPhys’ CLI and engineering standards, ensuring that configuration choices and provenance are first‑class citizens from day one. When DVH computation lands in subsequent sprints, these foundations make results reproducible, reviewable, and suitable for clinical QA workflows at Australian centres and beyond.*
