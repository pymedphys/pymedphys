# PyMedPhys DVH

A clinically‑oriented, cross‑modality, high‑precision dose–volume histogram engine for Python 3.12/3.13 (Windows/macOS/Linux)

### Primary goals

- A trustworthy, open, clinically usable DVH engine for QA, covering photons (including SRS/SBRT), protons and brachytherapy (any case that provides a 3D dose grid).

- Best‑practice numerics with tunable speed↔accuracy parameters and a formal validation harness against analytical ground truth (Nelms suite) and precision/uncertainty characterisation (Pepin method).

- First‑class integration with PyMedPhys: importable as pymedphys.dvh, leveraging pymedphys._interp.interp (trilinear) by default.

- Production‑grade engineering: metadata/audit, reproducibility, test evidence, and performance accelerators (Numba/CuPy).

> Why the fuss? DVH results vary across systems due to choices in voxelisation, interpolation, supersampling, end‑capping, binning, etc., and these differences can be clinically material—especially for small volumes and steep gradients (e.g., SRS/SBRT, protons). Recent studies document precision spreads of ~1–3% across commercial engines and much larger errors for sub‑cc targets if poorly handled. We will build in the mitigations as first‑class, configurable features and quantify residual imprecision.

## 1) Scope & requirements (condensed)

### 1.1 Clinical scope

- **Modalities:** External beam photons (including SRS/SBRT), protons, brachytherapy (provided as RTDOSE grids).

- **Workflows:** Independent plan QA; cross‑system DVH comparison; commissioning/periodic QA of DVH calculators; small‑structure analysis (e.g., D_0.03cc, PCI/MGI for SRS).

- **CT optional:** When present, used for geometric consistency and (optionally) to infer end‑cap spacing; otherwise the RTSTRUCT Z‑positions are authoritative.

### 1.2 Technical scope

- Python **3.12** and **3.13** on Windows/macOS/Linux.

- **API + CLI**; pure‑Python with optional accelerators (Numba, CuPy). No GUI initially.

- DICOM IO via `pydicom`; geometry via NumPy; polygon ops (including boolean) implemented in-house.

- **Reproducibility & audit:** structured run metadata (versions, config, seeds, input file hashes) persisted with outputs.

### 1.3 Accuracy & performance goals

- **Accuracy:** With “conservative” settings, achieve ≤ 0.1% error against the Nelms analytical benchmarks across our full matrix of geometric/dose cases; match analytical D_x% and V_yGy within 2 decimal places for standard grid spacings.

- **Precision characterisation:** Implement Pepin’s uncertainty band from stair‑step DVHs and report median/IQR precision consistent with their methodology (and expose it to users).

- **Performance:** For typical clinical ROI (10–500 cc) and 3 mm dose grids, default preset completes < ~2–5 s per structure on CPU; large ROIs and “max accuracy” settings may be longer; GPU path to accelerate supersampling & binning.

## 2) Design principles & literature‑backed choices

- **3D, not 2D:** Always model the ROI volumetrically (not just slice prisms) with 3D supersampling to mitigate stair‑steps and capture end‑caps—mirroring what distinguished higher‑precision systems in Pepin (e.g., heavy supersampling) and addressing failure - modes identified by Nelms and Ebert.

- **Shape‑based interslice interpolation (SBI):** Default to Herman et al. “shape‑based interpolation” to round interslice transitions and end‑caps, with alternatives selectable (right prism, truncate). Systems that skipped SBI showed larger biases and step - artefacts.

- **End‑capping choices matter:** Provide explicit, transparent end‑cap modes; track them in metadata. Different vendors’ choices (rounded vs half‑slice) materially shift volume extrema and extremum doses—users must be able to mimic their TPS.

- **Dose–structure alignment & interpolation:** Use trilinear interpolation (PyMedPhys’ fast path) by default; expose nearest/linear/cubic and point‑inside rules. Avoid relying solely on original dose voxel centres; supersample within ROI in 3D to defeat - aliasing.

- **Bin resolution:** Make DVH binning dynamic and fine‑grained (≥10 000 bins), with an option to emulate fixed‑width bins. Both dynamic and fixed schemes exist in clinical products and can influence perceived precision.

- **Small‑volume safeguards:** Detect and flag small volumes (e.g., <1 cc) and sparse‑slice structures; surface advisory tolerances based on recent SRS/SBRT evidence (e.g., D95 variability up to ~9% for very small volumes; PCI/MGI can deviate markedly).

## 3) Architecture & modules

```bash
pymedphys/
  _dvh/
    __init__.py                # re-export API as pymedphys.dvh
    api.py                     # public API surface
    config.py                  # DVHConfig dataclass + presets
    dicom_io.py                # DICOM loaders (RTSTRUCT/RTDOSE/CT) + transforms
    geometry.py                # contour → volume voxelisation (SBI & alternatives)
    endcaps.py                 # end-cap strategies
    inclusion.py               # point-in-polygon with holes (even-odd / winding), rings
    sampling.py                # 3D supersampling strategies (CPU/CuPy), stratified options
    dose_interp.py             # wrappers around pymedphys._interp.interp + fallbacks
    histogram.py               # differential/cumulative DVHs, dynamic/fixed bins
    metrics.py                 # D_x%, V_yGy, D_0.03cc, near-min/max, PCI/MGI, etc.
    precision.py               # Pepin uncertainty-band algorithm implementation
    sweep.py                   # speed↔accuracy parameter sweeps + reporting
    audit.py                   # run metadata capture (config, versions, hashes)
    cli.py                     # CLI entrypoints
tests/
  dvh/
    data/                      # Nelms data & our fixtures (see §10)
    unit/ integration/ regression/ performance/
```

### Core dataclasses

- **DoseGrid:** values (float32), shape (Z,Y,X), origin (x0,y0,z0), spacing (dx,dy,dz), orientation (patient LPS), units (Gy).

- **Structure3D:** list of 2D contours per axial plane (with nested rings), plane positions, orientation metadata.

- **DVHConfig:** knobs (see §5), including end‑cap mode, supersampling factors/targets, interpolation mode, inclusion rule, binning strategy, precision analysis on/off, GPU on/off.

## 4) Algorithms (pipeline)

### 1. Load & reconcile geometry

- Read RTSTRUCT, RTDOSE (and CT if present) via dicom_io.

- Verify coordinate frames; build transforms dose↔CT↔struct space; handle mismatched origins/spacings robustly (we will not assume matching grids). (Ebert demonstrated such mismatches are common across sites.)

### 2. Voxelise ROI (3D)

- In‑slice: polygon scan‑conversion with holes/rings via even–odd rule; robust to degenerate vertices; support diverging structures (1 contour splitting into 2 on next slice).

- Between slices: **shape‑based interpolation (SBI)** is default; alternatives: right‑prism half‑slice, truncate, half‑slice with max‑cap‑mm (to emulate ProKnow’s 1.5 mm limit if desired).

- End‑caps: strategy separately chosen (see §5.3). SBI end‑caps produce rounded tips; right‑prism extends by half slice; truncate places caps at last slice. (Commercial choices here were a major source of differences.)

### 3. Supersample within ROI (3D)

- Generate quasi‑uniform sample points within the voxelised ROI volume.

- Modes: target **N_points** (e.g., 100 000 default), or **subvoxel size** target, or **grid factor** (e.g., 3×,5×,7×) in (x,y,z). Ensure odd factors so samples include original dose grid planes (reduces miss of extrema). (This mirrors the effective strategies in Pepin/Nelms and avoids aliasing ceiling.)

### 4. Interpolate dose

- Default: `pymedphys._interp.interp` (trilinear). Alternatives: nearest/cubic (optional - needs implemented).

- For *reported* D_min/D_max, we will also probe interpolated dose at original contour vertices (surface points), as some precise implementations do to avoid missing surface extrema.

### 5. Histogram

- Differential DVH → cumulative DVH (volume [cm³] or fraction).

- Binning:
  - **dynamic (default):** choose bin width so that we have ≥10 000 bins over [D_min, D_max] (cap at 100 000).
  - **fixed:** user‑chosen bin width (e.g., 0.01 Gy). (Varied DVH resolutions across vendors drive visible stair‑steps.)

### 6. Metrics

- D_x% (5–95% step 1%), V_yGy (user list), near‑max/min (e.g., D_0.03cc), mean/min/max.

- SRS metrics: **PCI** and **MGI** as per Walker & Byrne (with the synthetic Gaussian prescription definition when used in validation mode).

### 7. Precision/uncertainty (optional but on by default for QA)

- Implement Pepin’s “stair‑step band” method: fit analytical form (for known shapes) or best‑fit smooth surrogate; detect step corners; compute upper/lower bound fits; report percent‑difference distribution across D_x% and extrema. Expose median/IQR; plot band.

- For clinical (unknown ground truth) shapes, optionally compute proxy precision indicators (e.g., step amplitude statistics), plus parameter‑sweep sensitivity summaries (see §6.5).

## 5) Configuration & presets

### 5.1 Global presets (user‑selectable)

- `"clinical_qa"` **(default)**: good balance of time/precision for typical ROIs.

- `"srs_small_volume"`: aggressive 3D supersampling; SBI end‑caps; fine bins; surface‑point extrema probe; warnings if volume < 1 cc or slice separation sparse. (Walker & Byrne highlight large variability below ~1 cc.)

- `"max_accuracy"`: push all knobs to conservative extremes to target ≤0.1% error vs Nelms.

- `"fast_preview"`: coarse subvoxel and fewer bins; suitable for fast iteration (clearly marked “preview – not for decisions”).

### 5.2 Key knobs (user configurable)

- **Supersampling:** `mode={"target_points","target_subvoxel_mm","grid_factor"}`; defaults: `target_points=100_000` inside ROI.

- **Interpolation:** `tri_linear` (default) | `nearest` | `cubic`.

- **Inclusion rule:** even–odd vs winding number; *treat holes/rings correctly*.

- **Inter‑slice interpolation:** `shape_based` (default) | `right_prism`.

- **End‑caps:** `truncate` | `half_slice` | `shape_based` (default) | `half_slice_with_max_mm=1.5`.

- **DVH bins:** `dynamic` (`min_bins=10_000`, `max_bins=100_000`) or `fixed` (`bin_width_Gy`).

- **D_min/D_max strategy:** `volume_samples_only` | `+surface_vertices` (default).

- **GPU:** `gpu=False|True` (CuPy path); `jit=True|False` (Numba path).

- **Dose units:** Gy (default) with percent conversions against a reference dose (prescription).

- **Uncertainty:** `precision_analysis=True|False` (Pepin method if analytical; proxy if clinical).

### 5.3 Recommended defaults per modality

- **Conventional EBRT QA:** `target_points≈50–100k`, SBI+shape‑based end‑caps, dynamic bins (~10–50k), trilinear.

- **SRS/SBRT:** `target_points ≥ 200k` or `grid_factor≥5×` in z if CT slice spacing ≥1 mm; SBI end‑caps; dynamic bins (≥50k); explicit D_0.03cc reporting; enable warnings for <1 cc.

- **Protons:** as SRS/SBRT (steeper gradients).

- **Brachy:** same; accept dose grids from TPS (future).

## 6) Interfaces

### 6.1 Python API (examples)

```python
import pymedphys as pmp
from pymedphys.dvh import compute_dvh, DVHConfig, load_dicom_plan

plan = load_dicom_plan(rtstruct_path, rtdose_path, ct_path=None)
cfg = DVHConfig.preset("clinical_qa").replace(
    endcaps="shape_based", target_points=100_000, precision_analysis=True
)

dvh, metrics, report = compute_dvh(
    dose=plan.dose, structure=plan.structures["Parotid_L"],
    config=cfg, reference_dose_Gy=66.0
)

print(metrics["D95_Gy"], metrics["D0.03cc_Gy"])
```

### 6.2 CLI

```css
pmp-dvh compute \
  --rtstruct RS.dcm --rtdose RD.dcm --ct CT/ \
  --structure "PTV_66" \
  --preset srs_small_volume \
  --ref-dose 24 \
  --out dvh_ptv66.json --plot dvh_ptv66.png
```

#### Outputs

- DVH curve (differential & cumulative); metrics JSON; optional plots; **audit JSON** including: package versions, Git SHA, config, input hashes (DICOM SOPInstanceUIDs & file checksums), date/time, hostname; “computed by PyMedPhys DVH”.

## 7) Validation & uncertainty reporting

### 7.1 Ground‑truth validation (Nelms 2015)

- Use the Nelms analytical datasets (sphere, cylinder, cone; linear gradients; various slice/dose spacings), exercising the **three Nelms test archetypes** (vary dose grid; match grids to slice spacing; rotated vs aligned). Expected behaviours and failure modes are well‑documented. We will target ≤0.1% with the `max_accuracy` preset and show error behaviour vs parameter relaxations.

#### Acceptance criteria (subset)

- Volume within 0.05% (rounded caps mode enabled where appropriate).

- D_min/D_max match analytical when end‑caps are considered (with surface‑vertex probe on).

- D_x% errors ≤0.1% (most cases) under `max_accuracy`; ≤1% under `clinical_qa`.

- Reproduce known vendor pitfalls (for regression): toggling end‑caps should recreate biases noted by Nelms (e.g., including cap volume but excluding cap dose → wrong D_min/D_max).

### 7.2 Precision metric (Pepin 2022)

- Implement the stair‑step band algorithm to quantify precision as percent‑difference distribution between fitted best curve and bounding curves, and report median/IQR across geometries and grid perturbations. This will become a built‑in QA report users can run on their own system.

### 7.3 Clinical‑like sensitivity

- Emulate clinical variability experiments: vary slice/dose spacings and re‑compute for representative OARs/PTVs; report percent uncertainty of D_mean/D_max and D95 across the grid combinations, mirroring the clinical findings (Eclipse/ProKnow/MIM/RayStation examples).

### 7.4 Small‑volume advisories (Walker & Byrne 2024)

- When ROI < 1 cc or has ≤5–7 slices, emit a prominent log warning and attach contextual guidance (e.g., potential ~2–9% D95 variability sub‑20 cc; can reach ~10–20% for ~0.1 cc; PCI/MGI can deviate sharply). Encourage tighter sampling and careful tolerance setting.

### 7.5 Multicentre consistency (Ebert 2010)

- Include a gamma‑like DVH comparison harness (dose‑to‑agreement & volume‑difference criteria) to compare our DVH against imported TPS‑exported DVHs, as an additional, practical cross‑check (diagnostic only).

## 8) Test‑Driven Development plan (strict)

**Guiding practice:** Red tests first, smallest possible slice of functionality, then implement; property‑based tests where helpful; slow tests marked and run in CI nightly.

### 8.1 Test datasets (in repo)

- `pymedphys/tests/dvh/data/nelms/`… : The Nelms synthetic DICOM (structures, dose) + analytical curves and expected metrics.

- `…/pepinsuite/…` : Synthetic cone/cylinder scenarios to exercise precision band code; includes SI/AP gradients and grid matrices (reproducing Tables/Figs trends).

- `…/clinical_like/…` : A few anonymised/constructed plans (e.g., cochlea & penile bulb analogues) to test resampling variability reporting.

- `…/pathological/…` : Rings/holes, bifurcations (1→2 contours), non‑manifold edge cases, single‑slice structures, very thin shells, and small (<0.1 cc) targets.

- Seeded random generators for fuzz tests (e.g., random polygons with known inside/outside).

### 8.2 Unit tests (examples)

- **Geometry:** in‑slice inclusion (even‑odd vs winding) with holes; shape‑based interpolation continuity; end‑cap modes.

- **Sampling:** coverage uniformity & reproducibility (with seed).

- **Interp:** exactness at grid points; trilinear vs PyMedPhys interp parity.

- **Histogram:** bin edge handling; cumulative monotonicity; units.

- **Metrics:** D_x%/V_yGy inversions; D_0.03cc; PCI/MGI definitions.

- **Precision:** reproduce band widths and example distributions from Pepin figures (within tolerance).

### 8.3 Integration tests

- Full DVH on Nelms cases across all grid spacings and orientations; assert tolerances (two presets: clinical_qa and max_accuracy).

- Cross‑check: same case with different end‑cap modes; verify expected shifts in min/max/volume (as reported in Pepin & Nelms).

### 8.4 Regression tests

- Lock in results for representative structures/doses and our presets; changes require explicit approval.

- Include DVH gamma‑like comparisons similar to Ebert’s approach to guard against unnoticed drift.

### 8.5 Performance tests

- Benchmarks for typical OAR (e.g., parotid), large ROI (liver), and small SRS lesions with CPU vs GPU vs Numba; assert max runtimes for presets on CI runners.

### 8.6 CI (GitHub Actions)

- Matrix: OS (win/mac/linux) × Python (3.12, 3.13).

- Stages: lint/typecheck → unit → fast integration → (nightly) slow validations & performance.

- Artefacts: HTML coverage; validation reports (PDF/PNG); wheel sdist.

## 9) Speed vs accuracy exploration (built‑in)

- `pymedphys.dvh.sweep.run()` takes a structure and dose, sweeps parameters (subvoxel size, points, binning, interp) and produces:

  - Error curves vs analytical (Nelms mode) or proxy precision indices (clinical mode).

  - Plots: error vs runtime; Pareto frontier; recommended presets for target bounds (e.g., “≤0.5% within 1.2 s”).

- This addresses your request to explore error vs inputs and guides users on the trade‑offs. (Pepin, Nelms and Ebert all underscore the sensitivity to discretisation and supersampling.)

## 10) Engineering details

- **Numerics:** float32 for storage, float64 for accumulators/metrics; Kahan compensation on sums; careful thresholding around polygon edges.

- **Robustness:** tolerant to non‑monotone Z‑ordering, duplicate points, near‑zero‑area contours; deduplicate planes within a tolerance; warn when CT and struct Z do not align (documented pitfall).

- **Parallelism:** vectorised NumPy; multi‑thread per‑structure histograms; optional CuPy GPU path for sampling + binning.

- **Logging:** structured (JSON) + human summary; WARNINGs for conditions known to degrade reliability (few slices; <1 cc; very coarse grids). (Walker & Byrne recommended caution/tolerances here.)

- **Docs:** narrative “How DVH choices change results” with examples reproducing literature phenomena (e.g., end‑cap bias, stair‑steps).

## 11) Roadmap & paired‑programming sprints

### Sprint 0 (infra)

- Repo layout; code style; DVHConfig; audit scaffolding; CLI stub.

### Sprint 1 (I/O & geometry)

- DICOM parsing; in‑slice voxelisation with holes; right‑prism interslice; truncate/half‑slice end‑caps; unit tests.

### Sprint 2 (SBI & end‑caps)

- Implement shape‑based interpolation (rounded interslice & end‑cap surfaces); exhaustive tests on synthetic shapes; perf profile.

### Sprint 3 (sampling & interpolation)

- 3D supersampling modes; integrate `pymedphys._interp.interp`; surface‑vertex extrema probe; property tests.

### Sprint 4 (histogram & metrics)

- Differential→cumulative; dynamic/fixed bins; D_x%/V_yGy; D_0.03cc; PCI/MGI; unit/integration tests.

### Sprint 5 (validation harness)

- Import Nelms datasets; analytical calculators; golden tolerances; CI gating.

### Sprint 6 (precision module)

- Pepin uncertainty‑band algorithm + reports; tests recreating published behaviours.

### Sprint 7 (sweeps & presets)

- Speed↔accuracy sweep tool; bake presets (`clinical_qa`, `srs_small_volume`, `max_accuracy`, `fast_preview`); docs.

### Sprint 8 (performance & GPU)

- Numba kernels; optional CuPy; performance CI; memory profiling.

### Sprint 9 (docs & examples)

- End‑to‑end notebooks; CLI recipes; “commission your TPS DVH” guide; include Ebert‑style gamma DVH compare utility.

### Sprint 10 (release & hardening)

- API freeze, versioning, CHANGELOG; wheels; long‑term support commitments.

- Pairing rhythm: 90‑minute blocks: red‑tests first, implement minimal pass, refactor; end each block with a micro‑demo and checklist update.

## 12) Clinical caveats baked into the tool

- **End‑cap sensitivity:** Present both D_max and D_0.03cc by default; flag if end‑cap choice materially changes near‑max metrics. (Near‑max is commonly preferred due to stability; our tool will show both so choices are conscious.)

- **Small volumes:** If <1 cc or ≤7 slices → show an advisory that DVH metrics can deviate several percent and that constraints should include DVH uncertainty tolerances per recent guidance/data.

- **Cross‑system comparisons:** Provide the DVH gamma‑like check and present differences alongside the chosen config so reviewers can see whether differences plausibly stem from methodological choices.

## 13) Deliverables

- `pymedphys.dvh` API + CLI; wheels for Py 3.12/3.13.

- Validation report (PDF) auto‑generated by CI: Nelms tables/plots with tolerances, Pepin precision stats, small‑volume advisories, and performance numbers.

- Example notebooks: “Reproducing end‑cap effects”, “SRS target sensitivity & tolerances”, “Protons & steep gradients”.

## 14) Risks & mitigations

- **Polygon robustness:** Degenerate or self‑intersecting contours → sanitise and warn; offer shapely path when present.

- **Memory/time blow‑ups:** Cap points by volume, adaptive grid factors, and expose progress bars & early‑stop for sweeps.

- **User confusion:** Defaults are sensible; every DVH carries its config and calculation note (“computed by PyMedPhys DVH”), matching your requirement to record provenance.

## 15) Acceptance checklist

- Passes all Nelms analytical cases under max_accuracy with ≤0.1% DVH errors; near‑zero bias trends across grid spacings/orientations.

- Pepin precision module reproduces stair‑step band behaviours and yields plausible medians/IQRs across our test matrix.

- Clear warnings/tolerances for small volumes per Walker & Byrne; PCI/MGI computed as specified.

- DVH gamma‑like comparison utility present; basic parity with Ebert’s methodology.

- CI green across OS/Python; docs complete; examples runnable end‑to‑end.

### Final notes on parameter recommendations (starting values)

- `clinical_qa`: `target_points=100k`, SBI + shape‑based end‑caps, dynamic bins (min 10k), trilinear, +surface extrema probe, Numba on, GPU off.

- `srs_small_volume`: `grid_factor=5×5×(5–7×)` (increase Z when slice spacing ≥1 mm), dynamic bins min 50k, +surface extrema probe, Numba on; suggest GPU on if available.

- `max_accuracy`: `target_points=300k` (or `grid_factor=7×`), SBI caps, dynamic bins up to 100k, trilinear, +surface extrema, Numba + GPU; expect ≤0.1% vs Nelms.
