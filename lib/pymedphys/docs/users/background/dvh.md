# PyMedPhys DVH — Configuration & Audit Guide

**Audience:** medical physicists, dosimetrists and developers commissioning, validating, or using the PyMedPhys DVH engine for clinical QA and research.

**Why this page?** DVH results do vary across systems due to choices in voxelisation, inter‑slice interpolation, end‑capping, dose sampling/supersampling, and histogram binning. Those differences are usually small for large structures, but for small volumes (especially SRS/SBRT) they can be clinically material. This guide shows how PyMedPhys makes those choices explicit (via DVHConfig) and how it records them (via the DVH audit JSON) so results are reproducible and defensible.

## 1) Why DVHs disagree — and why you should care

Multiple studies have shown measurable spreads in DVH metrics between commercial calculators even when given identical DICOM inputs. Effects grow as structure size decreases, slice spacing increases, or gradients steepen.

- **Small volumes & SRS/SBRT:** D95 variability up to ~9% for the smallest volumes; typically ~2% in 0.5–20 cc, ~1% for 20–70 cc; errors at DVH curve points up to ~10–20% for sub‑cc volumes; PCI errors up to ~40% and MGI up to ~75% around ~0.1 cc. These differences can flip a plan from “pass” to “fail” if tolerances are tight.

- **Across TPSs in trials:** With realistic clinical plans, gamma‑like comparisons of exported vs independently recomputed DVHs show non‑trivial spreads; minimum dose is especially sensitive to how end‑caps and edge interpolation are handled.

- **Algorithmic design choices:** Independent, analytic ground truth tests (spheres/cylinders/cones in linear gradients) show that end‑capping, dose supersampling, and inter‑slice interpolation materially affect DVH error and variability; insufficient 3D supersampling and inconsistent end‑cap handling are common failure modes.

Design response in PyMedPhys DVH: make every such choice explicit, provide sensible presets for typical clinical use, and always write a machine‑readable audit so others (including future‑you) can replicate or interrogate the result.

## 2) Configuration (DVHConfig) at a glance

`DVHConfig` is a dataclass that fully specifies how a DVH is computed. You can select a preset and adjust only what you need.

### 2.1 Presets

| Preset | Purpose | Key features (summary) |
| ------ | ------- | ---------------------- |
| `clinical_qa` (default) | Balanced accuracy & speed for typical OAR/PTV sizes | Trilinear dose interpolation, 3D supersampling to ~100k points, shape‑based inter‑slice interpolation, dynamic fine binning, surface‑vertex check for min/max |
| `srs_small_volume` | Sub‑cc to a few cc; steep gradients | Aggressive 3D supersampling (esp. in z), shape‑based end‑caps, ≥50k bins, surface‑vertex extrema probe, warnings for ≤7 slices/<1 cc |
| `max_accuracy` | Analytic validation / commissioning | Very high supersampling (or high grid factor), maximal bin count, full shape‑based interpolation & caps, determinism on; target ≤0.1% vs analytical DVH on Nelms datasets |
| `fast_preview` | Quick iteration (not for decisions) | Coarser sampling & bins, same algorithms |

### 2.2 Key knobs (selected)

- **Supersampling (3D within ROI):** choose a target number of points (e.g. target_points=100_000) or a grid factor (odd multiples like 3×, 5×, 7× to include original dose planes and avoid missing extrema). Heavier sampling is recommended for small volumes and coarse slice spacing.

- **Inter‑slice interpolation:** default shape‑based interpolation to round inter‑slice transitions; alternative right‑prism for emulation.

- **End‑caps:** truncate, half_slice, shape_based (default). End‑cap choice shifts min/max/near‑max metrics and must be recorded—differences here drove several published discrepancies.

- **Dose interpolation:** trilinear by default (via PyMedPhys interp), with optional nearest/cubic paths.

- **Inclusion rule (in‑slice polygon):** even–odd vs winding number; holes/rings handled.

- **DVH bins:** dynamic (≥10 000 bins across [Dmin, Dmax], default) or fixed width (e.g. 0.01 Gy).

- **Extrema strategy:** whether to probe original contour surface vertices (in addition to volumetric samples) to reduce missed min/max on structure surfaces.

- **Determinism:** set a fixed seed/layout for bit‑stable re‑runs (useful in CI and audits).

- **GPU / JIT:** optional CuPy and/or Numba accelerators (transparent to results).

> **Clinical caveat:** if the ROI volume < 1 cc or slice count ≤ 7, the engine emits a warning and suggests srs_small_volume (and, where applicable, reports PCI/MGI). For such sizes, published variability demands cautious tolerances.

## 3) Choosing settings by scenario

- **Conventional EBRT QA (typical OAR/PTV):** clinical_qa preset; nudge target_points to 50–100k if DVH steps are evident.

- **SRS/SBRT targets & steep gradients:** use srs_small_volume; increase z grid factor if CT slice spacing ≥1 mm; prefer shape‑based caps and surface‑vertex extrema. Expect larger inherent variability, so set clinical tolerances accordingly.

- **Commissioning vs analytic ground truth:** use max_accuracy; then relax to clinical_qa and quantify any drift; retain both audit JSONs. Compare against Nelms analytical curves and inspect end‑cap behaviour specifically.

- **Multicentre plan comparison:** compute DVHs with the same DVHConfig across the cohort; optionally run a DVH‑gamma like comparison (ΔV=1% of structure, ΔD=1% of Dmax; ≥95% bins pass) to flag outliers as per Ebert et al.

## 4) Python API examples

```python
import pymedphys as pmp
from pymedphys._dvh.api import compute_dvh
from pymedphys._dvh.config import DVHConfig

# Load your DICOM (helper omitted here for brevity)
dose = ...        # DoseGrid (values, spacing, origin, units)
structure = ...   # Structure3D, e.g. "PTV_24"

cfg = DVHConfig.preset("srs_small_volume").replace(
    target_points=200_000,
    endcaps="shape_based",
    precision_analysis=True,     # enable precision/uncertainty summary
)

dvh, metrics, audit = compute_dvh(
    dose=dose,
    structure=structure,
    config=cfg,
    reference_dose_Gy=24.0
)

print(metrics["D95_Gy"], metrics["D0.03cc_Gy"])
# You can serialise the audit dict yourself if you ran via API:
# Path("PTV_24.dvh.audit.json").write_text(json.dumps(audit, indent=2))
```

## 5) CLI examples

```bash
# Compute DVH and metrics; write sidecar audit JSON automatically.
pmp-dvh compute \
  --rtstruct RS.dcm --rtdose RD.dcm --ct CT/ \
  --structure "PTV_24" \
  --preset srs_small_volume \
  --ref-dose 24 \
  --out dvh_ptv24.json --plot dvh_ptv24.png
```

Outputs:

- `dvh_ptv24.json` — cumulative & differential DVH + metrics (Gy/cc and %).

- `dvh_ptv24.png` — optional plot.

- `dvh_ptv24.audit.json` — the audit (see below).

Flags:

- `--no-audit` to skip writing audit (discouraged outside rapid prototyping).

- `--audit-out` path.json to override the default sidecar name.

## 6) The DVH audit JSON

### 6.1 Purpose

The audit JSON is a structured, machine‑readable provenance record that travels with the DVH. It captures what inputs were used, which algorithms and parameters were chosen, what versions ran, and what warnings were raised. This directly addresses the traceability gaps that create apparent discrepancies across TPSs and tools (notably around end‑caps, supersampling, inter‑slice interpolation, and binning).

Because small‑volume DVHs are especially sensitive, the audit also includes small‑volume/slice‑count flags and precision indicators so downstream reviewers can apply appropriate clinical tolerances.

### 6.2 What’s inside (schema summary)

Top‑level keys you’ll see:

- `tool` / `version` / `git` / `python` — software identity (PyMedPhys, module version, Git commit).

- `timestamp` / `timezone` / `hostname` — when and where the run occurred.

- `inputs` — file paths, SOPInstanceUIDs and cryptographic hashes (SHA‑256) for RTSTRUCT, RTDOSE, CT; structure name; reference dose.

- `dose` — grid origin, shape, spacing (dx, dy, dz), units.

- `structure` — volume (cc), number of slices, z‑extent, holes/rings summary.

- `config` — the full `DVHConfig` (preset name, supersampling settings, interpolation modes, end‑caps, binning, inclusion rule, determinism seed, GPU/JIT flags).

- `runtime` — wall time, thread/GPU info.

- `metrics` — computed summary metrics (min/mean/max; D_x%; V_yGy; D_0.03cc if applicable).

- `precision` (if enabled) — Pepin‑style stair‑step/uncertainty indicators (median/IQR of |ΔV| or |ΔD| over the curve) and warnings if precision is degraded.

- `warnings` — e.g., small volume/sparse slices, extreme bin widths, non‑uniform slice spacing, CT/structure z‑misalignments.

- `notes` — free‑text, e.g., “computed by PyMedPhys DVH”.

### 6.3 Example (abridged)

```json
{
  "tool": "pymedphys.dvh",
  "version": "0.1.0",
  "git": "7b4f1c9",
  "python": "3.12.4",
  "timestamp": "2025-10-11T08:13:24Z",
  "hostname": "physics-ws07",
  "inputs": {
    "rtstruct": {"path": "RS.dcm", "sop_instance_uid": "...", "sha256": "..." },
    "rtdose":   {"path": "RD.dcm", "sop_instance_uid": "...", "sha256": "..." },
    "ct":       {"path": "CT/", "series_uid": "...", "sha256_manifest": "..." },
    "structure_name": "PTV_24",
    "reference_dose_Gy": 24.0
  },
  "dose": {"origin_mm": [x0,y0,z0], "spacing_mm": [dx,dy,dz], "shape_zyx": [Nz,Ny,Nx], "units": "Gy"},
  "structure": {"volume_cc": 0.82, "slice_count": 6, "z_extent_mm": 5.0, "rings": 0},
  "config": {
    "preset": "srs_small_volume",
    "supersampling": {"mode": "target_points", "target_points": 200000},
    "inter_slice": "shape_based",
    "endcaps": "shape_based",
    "interpolation": "trilinear",
    "inclusion_rule": "even_odd",
    "bins": {"mode": "dynamic", "min_bins": 50000, "effective_bins": 61248},
    "extrema_strategy": "volume_plus_surface_vertices",
    "deterministic_seed": 20251011,
    "gpu": false,
    "jit": true
  },
  "runtime": {"seconds": 1.84, "cpu_threads": 8, "gpu": null},
  "metrics": {
    "min_Gy": 11.9, "mean_Gy": 24.7, "max_Gy": 34.3,
    "D95_Gy": 23.0, "D0.03cc_Gy": 31.1,
    "Dx%_Gy": {"D98": 22.7, "D95": 23.0, "D50": 26.2, "D2": 32.9}
  },
  "precision": {"deltaV_median_pct": 0.3, "deltaV_IQR_pct": 0.6, "method": "pepin_stair_step"},
  "warnings": ["small_volume_lt_1cc", "sparse_slices_leq_7"]
}
```

### 6.4 How it’s used ongoing

- **Reproducibility:** Any audit record contains enough information to re‑instantiate the DVHConfig, re‑link the exact inputs (via SOP UIDs and hashes), and reproduce the DVH.

- **Commissioning & periodic QA:** Keep audits from max_accuracy analytic tests (Nelms suite) alongside those from clinical_qa. Diff the two to track drift over time or code changes.

- **Multicentre comparisons:** Include audits with shared DVH data so the receiving site can understand why an apparent difference occurred (e.g., different end‑caps or sampling). Ebert‑style DVH‑gamma can be re‑run on demand with the same config.

- **Small‑volume safeguards:** When an audit flags <1 cc and ≤7 slices, reviewers can immediately set appropriate tolerance margins, as recommended by recent evidence.

- **Data governance:** By default, the audit records SOPInstanceUIDs and cryptographic hashes—not patient identifiers. Paths are included only if you run locally; redact or omit them if exporting outside your organisation.

## 7) Validation & uncertainty reporting (what to expect)

- **Analytical (Nelms) validation:** With the max_accuracy preset, PyMedPhys DVH targets ≤ 0.1% error versus ground‑truth DVHs across spheres/cylinders/cones in linear gradients, and reproduces known end‑cap and supersampling sensitivities. The audit marks - the preset and effective bin count so you can contextualise any residual steps.

- **Precision characterisation (Pepin‑style):** The engine can summarise stair‑step behaviour as a precision band (median/IQR of |ΔV| or |ΔD|), with directionality (SI vs AP) noted, and attach that to the audit. Use this to discuss tolerances when CT slice spacing or dose grid resolution are coarse.

- **DVH‑gamma (Ebert‑style):** As a pragmatic check, compute DVH gamma between TPS‑exported and PyMedPhys DVHs at ΔV=1% / ΔD=1% with ≥95% bins pass expected under good agreement; coarser criteria (3%/2%) typically approach 100% for large volumes.

## 8) Practical tips & pitfalls

- **End‑caps decide extremum doses:** If your plan review depends on Dmin or near‑min metrics, end‑cap policy matters; record it and prefer near‑min (e.g., D98/D95) for stability. Some systems historically included cap volume but excluded cap dose in DVHs—PyMedPhys makes this choice explicit and auditable.

- **Odd grid factors reduce “misses”:** When supersampling, 3×/5×/7× along axes helps include original dose planes (reducing missed maxima/minima).

- **Slice spacing vs small targets:** If a ~3 mm radius sphere spans only a handful of slices, DVH steps and biases are expected regardless of the calculator; increase supersampling, use shape‑based interpolation, and treat constraints with appropriate uncertainty margins.

## 9) Appendix — Full `DVHConfig` (field reference)

(Field names as exposed by the Python API; CLI flags mirror these.)

- `preset: Literal["clinical_qa","srs_small_volume","max_accuracy","fast_preview"]`

- `supersampling: {mode: "target_points"|"grid_factor"|"target_subvoxel_mm", target_points?: int, grid_factor?: [int,int,int], target_subvoxel_mm?: float}`

- `interpolation: "trilinear"|"nearest"|"cubic"`

- `inclusion_rule: "even_odd"|"winding"`

- `inter_slice: "shape_based"|"right_prism"`

- `endcaps: "shape_based"|"half_slice"|"truncate"`

- `bins: {mode: "dynamic"|"fixed", min_bins?: int, max_bins?: int, bin_width_Gy?: float}`

- `extrema_strategy: "volume_samples_only"|"volume_plus_surface_vertices"`

- `deterministic_seed: Optional[int]`

- `gpu: bool, jit: bool`

- `precision_analysis: bool`

- `reference_dose_Gy: Optional[float] (for % dose scaling)`

Every computed DVH serialises the effective values (e.g., effective_bins) into the audit.

## 10) Appendix — Audit JSON (field reference)

- `tool`, `version`, `git`, `python`, `timestamp`, `timezone`, `hostname`

- `inputs`: `rtstruct`, `rtdose`, `ct` (paths/hashes/uids), `structure_name`, `reference_dose_Gy`

- `dose`: `origin_mm`, `spacing_mm`, `shape_zyx`, `units`

- `structure`: `volume_cc`, `slice_count`, `z_extent_mm`, `rings`

- `config`: full `DVHConfig` (including preset + all derived/effective values)

- `runtime`: seconds + hardware summary

- `metrics`: min/mean/max; common D_x%/V_yGy; near‑max (e.g., `D0.03cc_Gy` when applicable)

- `precision`: Pepin‑style indicators (optional)

- `warnings`: array of human‑legible strings

- `notes`: free‑text

## 11) Further reading (for context)

- **Plan checks flipping pass/fail across systems, small‑volume variability, and SRS metrics sensitivity:** Walker & Byrne, Clinical impact of DVH uncertainties.

- **Multicentre differences and DVH‑gamma approach for consistency checks:** Ebert et al., Comparison of DVH data from multiple TPSs.

- **Analytical ground truth datasets; why end‑caps, supersampling and surface probing matter:** Nelms et al., Methods, software and datasets to verify DVH calculations against analytical values.

-------------------------------------------------

### A final word

PyMedPhys DVH treats configuration as first‑class and records it. That’s deliberate: when a DVH value edges a constraint, the calculation method itself can be the true source of difference. With clear config and a complete audit, you can explain, reproduce, and—when needed—set appropriate tolerances backed by evidence.
