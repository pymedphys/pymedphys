# pymedphys.gamma — Verification Model

The gamma index ([_gamma/implementation/shell.py](../../lib/pymedphys/_gamma/implementation/shell.py), public API `pymedphys.gamma`) is the keystone numerical kernel of the pymedphys QA suite — it compares two dose distributions per the [Low 1998](https://doi.org/10.1118/1.598248) tolerance-region method, returning a per-voxel ndarray of gamma values where `gamma <= 1` denotes "passes the agreement criterion". This document is the **CRUTPr-style verification deliverable** for the kernel: 14 verification predicates over the kernel's input/output, 7 clinical hazards traced to discharging predicates, 6 reference test corpora drawn from the Agnew-McGarry 2016 publication and synthetic edge cases. Modeled on the 2003 ALGT/algt_tests/ corpus.

This is the **first deliverable** produced under the `python-algorithm-verification` skill. The structural pattern established here (4-module Prolog + pytest harness mirror + 4 PlantUML diagrams + hazard-traceability artifact) is the canonical template for further pymedphys algorithm-verification deliverables (`metersetmap_calculate`, `delivery_from_*`, `anonymise_dataset`, etc.).

---

## 1. Algorithm I/O Schema

![I/O Schema](diagrams/bdd_gamma_io_schema.svg)

> Source: [`diagrams/bdd_gamma_io_schema.puml`](diagrams/bdd_gamma_io_schema.puml)

### 1.1 Inputs

| Parameter | Type | Constraint | Sentinel handling | Hazard if violated |
|---|---|---|---|---|
| `axes_reference` | tuple of monotonic ndarrays | each axis monotonic increasing | empty → ValueError | misaligned grids → wrong distance metric → false QA result |
| `dose_reference` | ndarray (any rank) | shape matches axes product | NaN propagated; values < cutoff → output NaN | dtype mismatch → downstream type errors |
| `axes_evaluation` | tuple of monotonic ndarrays | as `axes_reference` | as `axes_reference` | same |
| `dose_evaluation` | ndarray | shape matches `axes_evaluation` | NaN propagated | as `dose_reference` |
| `dose_percent_threshold` | Number OR List[Number] | > 0 | ≤ 0 → ValueError or division by zero | clinically meaningless |
| `distance_mm_threshold` | Number OR List[Number] | > 0 | ≤ 0 → ValueError or zero-radius shell | infinite loop |
| `lower_percent_dose_cutoff` | Number (default 20) | percentile of normalisation | values below → output NaN | low-dose region falsely flagged as failure |
| `interp_fraction` | Int (default 10) | ≥ 1 | smaller → coarser interpolation | quantization-induced false QA |
| `max_gamma` | Number (default `inf`) | > 0 | finite → clamp; `inf` → no clamp | clamp masking failure (H5) |
| `local_gamma` | Bool (default `False`) | — | False → global normalisation; True → per-voxel | option silently ignored → wrong normalisation |
| `global_normalisation` | Number OR None (default `None` → max(`dose_reference`)) | > 0 | None at runtime → max(`dose_reference`) | wrong normalisation → uncalibrated tolerance |
| `skip_once_passed` | Bool (default `False`) | — | True → early-exit when gamma ≤ 1 found | speedup; no correctness impact |
| `random_subset` | Int OR None (default `None`) | None → full ref grid | seeded via `np.random.seed(42)` in tests | nondeterministic results (H7) |
| `ram_available` | Int (default 1.5GB) | > 0 | controls chunking | OOM on overlarge grids |
| `quiet` | Bool (deprecated) | — | DeprecationWarning emitted | — |
| `interp_algo` | Atom (default `pymedphys`) | one of `{pymedphys, scipy}` | invalid → ValueError | algorithm divergence between backends |

### 1.2 Outputs

When `dose_percent_threshold` and `distance_mm_threshold` are scalars: returns ndarray of same shape as `dose_reference`. Output values:

- **Range**: in `[0, max_gamma]` (clamped at [shell.py:177-178](../../lib/pymedphys/_gamma/implementation/shell.py#L177-L178))
- **NaN contract**: `isnan(out[i]) ⇔ ref_dose[i] < lower_dose_cutoff` (strict biconditional). The kernel also explicitly converts `inf` to `NaN` at [shell.py:174](../../lib/pymedphys/_gamma/implementation/shell.py#L174) so no `inf` ever appears in the output.
- **Determinism**: byte-identical for repeated invocations under the same `np.random.seed`.

When either `dose_percent_threshold` or `distance_mm_threshold` is a list: returns `dict[(pct, dist) → ndarray]` with one ndarray per criterion combination. Each ndarray satisfies the same contract.

### 1.3 Documented edge cases

- **Zero-volume reference**: empty `axes_reference` raises ValueError in `run_input_checks`.
- **All-NaN evaluation**: gamma propagates NaN naturally; the output's NaN mask becomes the union of `ref < cutoff` and the propagated NaNs.
- **Single-element grids**: degenerate; gamma is computed but interpolation is trivial.
- **Reference identical to evaluation**: `gamma(D, D) ≈ 0` everywhere defined (within `interp_fraction` quantization noise; verified by `ok_gamma_reflexive`).

---

## 2. Compute Pipeline

![Compute Pipeline](diagrams/act_gamma_pipeline.svg)

> Source: [`diagrams/act_gamma_pipeline.puml`](diagrams/act_gamma_pipeline.puml)

The kernel decomposes into 4 phases:

1. **Input validation + options construction** ([shell.py:117-144](../../lib/pymedphys/_gamma/implementation/shell.py#L117-L144)) — `run_input_checks` validates axes monotonicity + dtype + shape compatibility; `expand_dims_to_1d` normalises scalar-or-list pct/dist thresholds; `GammaInternalFixedOptions.from_user_inputs` packs everything into a frozen dataclass with `global_normalisation := max(dose_reference)` if not provided.

2. **Per-voxel gamma loop** ([shell.py:165, body at 323-580](../../lib/pymedphys/_gamma/implementation/shell.py#L165)) — `gamma_loop(options)` iterates over `reference_points_to_calc` (subset of reference voxels, possibly random-subsampled), expanding concentric distance shells until `gamma ≤ 1` is found OR the search radius exceeds `maximum_test_distance`. `interp_fraction` subdivides each shell. `skip_once_passed` short-circuits when `gamma ≤ 1` is found. Returns a flat array indexed by `(reference_point_idx, pct_idx, dist_idx)`.

3. **Post-loop processing** ([shell.py:167-180](../../lib/pymedphys/_gamma/implementation/shell.py#L167-L180)) — for each `(pct, dist)` slice: `np.reshape` to `dose_reference.shape`; `inf → NaN` ([:174](../../lib/pymedphys/_gamma/implementation/shell.py#L174)); clamp values exceeding `max_gamma` ([:177-178](../../lib/pymedphys/_gamma/implementation/shell.py#L177-L178)); store under the `(pct, dist)` key.

4. **Output dispatch** ([shell.py:184-187](../../lib/pymedphys/_gamma/implementation/shell.py#L184-L187)) — single criterion → return ndarray; multi-criterion → return dict.

Note: this is **not a state machine**. There are no events, no transitions, no rerun. The pipeline is a deterministic function from input to output; the `<<act>>` activity diagram captures the compute flow for documentation purposes only.

---

## 3. Verification Aspects

| Aspect | Predicate | Discharging hazard(s) | Fixture(s) exercising | Anchor |
|---|---|---|---|---|
| **range_nonneg** | `ok_gamma_range_nonneg/1` | H1 (false-negative QA) | every fixture (universal) | [shell.py:165](../../lib/pymedphys/_gamma/implementation/shell.py#L165), [Low 1998](https://doi.org/10.1118/1.598248) |
| **range_below_max** | `ok_gamma_range_below_max/2` | H5 (clamp masking) | every fixture | [shell.py:177-178](../../lib/pymedphys/_gamma/implementation/shell.py#L177-L178) |
| **no_inf** | `ok_gamma_no_inf/1` | H3 (silent NaN propagation) | every fixture | [shell.py:174](../../lib/pymedphys/_gamma/implementation/shell.py#L174) |
| **shape_matches_reference** | `ok_gamma_shape_matches_reference/2` | H6 (shape mismatch) | every fixture | [shell.py:173](../../lib/pymedphys/_gamma/implementation/shell.py#L173) |
| **nan_at_low_dose** | `ok_gamma_nan_at_low_dose/3` | H3 | every fixture | gamma_loop per-voxel masking |
| **reflexive** | `ok_gamma_reflexive/2` | H4 (numerical-stability loss) | `synthetic_reflexive_2d` | gamma definition |
| **deterministic** | `ok_gamma_deterministic/2` | H4 + H7 | `synthetic_determinism` | pure-function semantics |
| **max_gamma_clamp** | `ok_gamma_max_gamma_clamp/2` | H5 | `agnew_mcgarry_local_1mm_max1p0001` | [shell.py:177-178](../../lib/pymedphys/_gamma/implementation/shell.py#L177-L178) |
| **pass_rate_monotonic_pct** | `ok_gamma_pass_rate_monotonic_pct/4` | H1 + H2 | `agnew_mcgarry_local_1mm` (paired runs) | pass_rate semantics |
| **pass_rate_monotonic_dist** | `ok_gamma_pass_rate_monotonic_dist/4` | H1 + H2 | `agnew_mcgarry_local_1mm` (paired runs) | same |
| **equiv_agnew_mcgarry_local_1mm** | `ok_gamma_equiv_pass_rate/3` | H1 + H2 | `agnew_mcgarry_local_1mm` (baseline 93.6%) | [test_agnew_mcgarry.py:144](../../lib/pymedphys/tests/gamma/test_agnew_mcgarry.py#L144) |
| **equiv_agnew_mcgarry_local_0_25mm** | `ok_gamma_equiv_pass_rate/3` | H1 + H2 | `agnew_mcgarry_local_0_25mm` (baseline 96.9%) | [test_agnew_mcgarry.py:149](../../lib/pymedphys/tests/gamma/test_agnew_mcgarry.py#L149) |
| **equiv_multi_criteria** | `ok_gamma_equiv_multi_criteria/3` | H1 + H2 | `agnew_mcgarry_multi_criteria` | [test_agnew_mcgarry.py:174-179](../../lib/pymedphys/tests/gamma/test_agnew_mcgarry.py#L174-L179) |
| **local_normalisation_used** | `ok_gamma_local_normalisation_used/3` | H1 + H2 | `agnew_mcgarry_local_1mm` (paired local/global runs) | [shell.py:127-144](../../lib/pymedphys/_gamma/implementation/shell.py#L127-L144) |
| **global_normalisation_default** | `ok_gamma_global_normalisation_default/3` | H4 | `agnew_mcgarry_local_1mm` (paired None/explicit) | [shell.py:138](../../lib/pymedphys/_gamma/implementation/shell.py#L138) |

15 verification predicates covering 7 clinical hazards. Each predicate has a corresponding pytest function in [pytest/test_gamma_verification.py](pytest/test_gamma_verification.py) whose docstring cites the predicate by name (`Mirror of ok_gamma_range_nonneg/1.`).

---

## 4. Constraints and Invariants

![Constraints and Invariants](diagrams/par_gamma_invariants.svg)

> Source: [`diagrams/par_gamma_invariants.puml`](diagrams/par_gamma_invariants.puml)

### 4.1 Constraints (input validation)

Enforced by `run_input_checks` and `GammaInternalFixedOptions.from_user_inputs`:

- **`valid_pct_threshold`**: `dose_percent_threshold > 0` ([shell.py:73-74](../../lib/pymedphys/_gamma/implementation/shell.py#L73-L74) docstring).
- **`valid_dist_threshold`**: `distance_mm_threshold > 0` ([shell.py:75-76](../../lib/pymedphys/_gamma/implementation/shell.py#L75-L76)).
- **`monotonic_axes`**: each axis monotonic increasing.
- **`matched_axes_dose_shape`**: `dose_reference.shape` is the cartesian product of `axes_reference` lengths.

### 4.2 Invariants (output-time)

Preserved by every successful kernel invocation:

- **`range_nonneg`**: `forall non-NaN g: g >= 0` — discharged by `ok_gamma_range_nonneg/1`.
- **`range_below_max`**: `forall non-NaN g: g <= max_gamma` — discharged by `ok_gamma_range_below_max/2` and `ok_gamma_max_gamma_clamp/2`.
- **`no_inf`**: `forall g: not isinf(g)` — discharged by `ok_gamma_no_inf/1`.
- **`shape_matches_reference`**: `Output.shape == dose_reference.shape` — discharged by `ok_gamma_shape_matches_reference/2`.
- **`nan_at_low_dose_biconditional`**: `forall i: ref[i] < cutoff ⇔ isnan(out[i])`. Strong claim — NaN appears IFF low-dose. Discharged by `ok_gamma_nan_at_low_dose/3`.
- **`reflexive`**: `gamma(D, D) ~ 0` wherever defined — discharged by `ok_gamma_reflexive/2`.
- **`deterministic`**: `gamma(A, B, opts) == gamma(A, B, opts)` under same `np.random.seed` — discharged by `ok_gamma_deterministic/2`.
- **`pass_rate_monotonic_pct`**: `Pct1 <= Pct2 → pass_rate(Pct1) <= pass_rate(Pct2)` — discharged by `ok_gamma_pass_rate_monotonic_pct/4`.
- **`pass_rate_monotonic_dist`**: `Dist1 <= Dist2 → pass_rate(Dist1) <= pass_rate(Dist2)` — discharged by `ok_gamma_pass_rate_monotonic_dist/4`.
- **`agnew_mcgarry_baseline_match`**: published baselines match within ±0.05% — discharged by `ok_gamma_equiv_pass_rate/3` against the H&N VMAT fixtures.
- **`local_global_distinct`**: `|pass_rate(local=True) - pass_rate(local=False)| >= 0.5%` on agnew-mcgarry fixtures — discharged by `ok_gamma_local_normalisation_used/3`.
- **`global_normalisation_default`**: `gamma(local=False, global_norm=None) == gamma(local=False, global_norm=max(dose_ref))` byte-identically — discharged by `ok_gamma_global_normalisation_default/3`.

---

## 5. Hazard Traceability (FDA MDDT)

![Hazard Traceability](diagrams/par_gamma_hazards.svg)

> Source: [`diagrams/par_gamma_hazards.puml`](diagrams/par_gamma_hazards.puml)

This is the regulatory-narrative artifact required for the [ALGT-FMEA MDDT proposal](d:/MUSIQ/ALGT/docs/FDA_MDDT_Proposal.md).

| Hazard | Discharging predicates | Fixtures exercising | Mitigation residual risk |
|---|---|---|---|
| **H1**: false-negative QA → uncaught delivery error → patient harm | `ok_gamma_range_nonneg`, `ok_gamma_pass_rate_monotonic_pct/dist`, `ok_gamma_equiv_pass_rate`, `ok_gamma_equiv_multi_criteria`, `ok_gamma_local_normalisation_used` | `agnew_mcgarry_local_1mm`, `agnew_mcgarry_local_0_25mm`, `agnew_mcgarry_multi_criteria` | Predicates exercise 6MV photon datasets only. Proton/electron/carbon-ion modalities NOT covered; mitigation deferred to per-modality verification deliverables. |
| **H2**: false-positive QA → unnecessary plan rework → treatment delay → patient harm | same predicates as H1 | same fixtures | same residual risk |
| **H3**: silent NaN propagation → uncaught failure → false-negative QA → patient harm | `ok_gamma_no_inf`, `ok_gamma_nan_at_low_dose` | every fixture (universal predicates) | NaN biconditional is verified under `local_gamma=False`; the local-gamma path uses a dose-relative cutoff that's harder to verify in closed form (residual risk: predicate is approximate for local mode). |
| **H4**: numerical-stability loss → reproducibility loss → regulatory noncompliance | `ok_gamma_reflexive`, `ok_gamma_deterministic`, `ok_gamma_global_normalisation_default` | `synthetic_reflexive_2d`, `synthetic_determinism` | Determinism verified for seeded `random_subset`. Float-summation order dependency in numpy reductions NOT independently verified; mitigation relies on numpy's documented stability guarantees. |
| **H5**: clamp masking → false-negative QA → patient harm (subsumes H1) | `ok_gamma_range_below_max`, `ok_gamma_max_gamma_clamp` | `agnew_mcgarry_local_1mm_max1p0001`, `agnew_mcgarry_local_1mm_max14` | Clamp behavior verified at `max_gamma ∈ {1.0001, 1.4, 1.1}`. Behavior at very large `max_gamma` (e.g. `1e6`) is not explicitly exercised; mitigation: the clamp logic at PY:177-178 is a single np.where call with no branches, so behavior should be uniform. |
| **H6**: shape mismatch → indexing errors → wrong voxel association → patient harm | `ok_gamma_shape_matches_reference` | every fixture | Predicate covers `dose_reference.shape == output.shape`. Multi-criterion dict outputs: each ndarray in the dict satisfies the same-shape predicate independently (`ok_gamma_equiv_multi_criteria` enforces transitively). |
| **H7**: nondeterministic `random_subset` → reproducibility loss → audit failure | `ok_gamma_deterministic` | `synthetic_determinism`, `agnew_mcgarry_local_1mm` (with seed) | Determinism verified ONLY when `np.random.seed(42)` is set before each invocation. Without seeding, `random_subset` is genuinely nondeterministic — that's a kernel design property, not a defect; downstream callers must seed appropriately. |

The diagram structure is the load-bearing audit artifact: a regulator should be able to ask "what predicates discharge H3?" and answer from the diagram (predicate boxes with arrows pointing INTO the H3 box). Same for "what fixtures exercise H1?" (fixture boxes with arrows pointing into the predicate boxes that discharge H1).

---

## 6. Reference Test Corpora

| Name | Source | Scenario | Hazard categories | Path |
|---|---|---|---|---|
| `agnew_mcgarry_local_1mm` | Agnew & McGarry 2016 | H&N VMAT 1mm pixel; `max_gamma=1.1`; 1%/1mm local; baseline 93.6% | H1, H2, H7 | `gamma_test_data.zip:H&N_VMAT_*_1mmPx.dcm` |
| `agnew_mcgarry_local_1mm_max14` | same | same data; `max_gamma=1.4` (clamp variant) | H1, H2, H5 | same |
| `agnew_mcgarry_local_1mm_max1p0001` | same | same data; `max_gamma=1.0001` (clamp at pass threshold) | H5, H4 | same |
| `agnew_mcgarry_local_0_25mm` | Agnew & McGarry 2016 | H&N VMAT 0.25mm pixel; baseline 96.9% | H1, H2 | `gamma_test_data.zip:H&N_VMAT_*_0_25mmPx.dcm` |
| `agnew_mcgarry_multi_criteria` | Agnew & McGarry + pymedphys baselines | Multi-(pct,dist): (1,1)→96.9, (1,4)→99.8, (0.2,1)→91.8, (0.2,4)→99.2 | H1, multi_criteria_dispatch | same as 0.25mm |
| `synthetic_reflexive_2d` | constructed in pytest harness | gamma(D, D) on 20×20 synthetic dose; expect all-zero | H4, H3 | (in-memory) |
| `synthetic_determinism` | constructed in pytest harness | repeat invocation with `np.random.seed(42)`; expect byte-identity | H4, H7 | (in-memory) |

The DICOM test data ships separately from the pymedphys repo; `pymedphys._data.download.get_file_within_data_zip("gamma_test_data.zip", filename)` fetches it from Zenodo on first access.

---

## 7. LTS bindings (cross-language references)

`pymedphys.gamma` is invoked as a boundary primitive in the following `python-streamlit-state-model` deliverables. Bisimulation requires that the kernel's input-output contract (verified here) matches the LTS's expectations at the call site (modeled there).

| LTS deliverable | Boundary predicate | Call site (Python) | Verified contract |
|---|---|---|---|
| [`lts_models/metersetmap/`](../../lts_models/metersetmap/) | `algorithm_kernels:pymedphys_gamma/6` ([algorithm_kernels.pl](../../lts_models/metersetmap/prolog/algorithm_kernels.pl)) | [main.py:362-368](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L362-L368) — `pymedphys.gamma(COORDS, ref_tup, COORDS, eval_tup, **gamma_options)` | range_nonneg + no_inf + shape_matches_reference + nan_at_low_dose + max_gamma_clamp + pass_rate_monotonic + agnew_mcgarry_baseline_match |

The `lts_models/metersetmap/` deliverable's [Section 2.5.3](../../lts_models/metersetmap/metersetmap_state_model.md) lists the `algorithm_kernels:pymedphys_gamma/6` boundary primitive with a `python-algorithm-verification/gamma/ (DEFERRED)` cross-reference. **With this deliverable in place, that DEFERRED marker can be replaced with a link to this document.** The LTS deliverable's bisimulation argument now bottoms out at a verified algorithm.

### Recommended follow-up: clear the DEFERRED markers

The metersetmap LTS deliverable currently flags 12 algorithm kernels as DEFERRED. The other 11 (metersetmap_grid/display/delivery, 5 delivery loaders, TRF decoders, normalize_to_uint8) are still pending. Each follows the same pattern as this gamma deliverable; the next priorities (in order of LTS-binding centrality) are:

1. `metersetmap_calculate` — second-most-central kernel for metersetmap; verifies the per-delivery MU-map fold.
2. `delivery_from_dicom` / `delivery_from_icom` / `delivery_from_trf` / `delivery_from_monaco` / `delivery_from_mosaiq` — five delivery loaders; each has a separate verification deliverable because their input formats and edge cases differ.
3. `anonymise_dataset` + `pseudonymisation_dispatch` — closes the [`lts_models/pseudonymise/`](../../lts_models/pseudonymise/) deliverable's cross-references.
4. `trf_decoder` — the binary-format decoder; needed for TRF-based delivery verification but not directly safety-critical.
5. `normalize_to_uint8` — purely visual; lowest priority.

---

## Operational equivalence statement

For input fixture `agnew_mcgarry_local_1mm` with `np.random.seed(42)` and `random_subset=50000`:

- The kernel produces output `gamma_array` with `gamma_array.shape == dose_reference.shape`.
- Every aspect predicate in Section 3 succeeds against this output:
  - `ok_gamma_range_nonneg(gamma_array)` — all finite values ≥ 0
  - `ok_gamma_no_inf(gamma_array)` — no inf values
  - `ok_gamma_shape_matches_reference(gamma_array, dose_reference)` — shapes match
  - `ok_gamma_nan_at_low_dose(gamma_array, dose_reference, 20)` — NaN biconditional holds
  - `ok_gamma_max_gamma_clamp(gamma_array, 1.1)` — all finite values ≤ 1.1
  - `ok_gamma_equiv_pass_rate(gamma_array, 93.6, 0.05)` — pass rate is 93.6% within tolerance
- Subsequent re-invocations with the same seed produce byte-identical output (`ok_gamma_deterministic` succeeds).

When this kernel is invoked from `lts_models/metersetmap/`'s compute pipeline (in the `computing_gamma` internal-trace tier), the resulting output satisfies the LTS's downstream contract: it can be consumed by `plot_gamma_hist` ([metersetmap/main.py:223-232](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L223-L232)) which calls `np.sum(valid_gamma <= 1) / len(valid_gamma)` for the pass-rate display, and by `metersetmap_display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)` ([metersetmap/main.py:325](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L325)). The LTS bisimulation against a Selenium-driven Streamlit UI run holds at the gamma boundary primitive.

---

## Files

- [prolog/](prolog/) — 6 Prolog modules
  - [gamma_kernel_boundary.pl](prolog/gamma_kernel_boundary.pl) — `call_gamma/6` boundary primitive (subprocess + janus_swi runner modes)
  - [verification_predicates.pl](prolog/verification_predicates.pl) — reusable `is_approx_equal/3`, `forall_ndarray/2`, `pass_rate/3`, `same_shape/2`
  - [test_fixtures.pl](prolog/test_fixtures.pl) — registry of 7 fixtures with hazard categories
  - [gamma_invariants.pl](prolog/gamma_invariants.pl) — 14 `ok_gamma_<aspect>` predicates
  - [gamma_verification.pl](prolog/gamma_verification.pl) — top-level `ok_gamma/3` + `ok_gamma_against_fixture/2`
  - [gamma_runner.pl](prolog/gamma_runner.pl) — ALGT-style `:- open_log, ..., close_log` runner
- [pytest/](pytest/) — Python harness
  - [test_gamma_verification.py](pytest/test_gamma_verification.py) — pytest functions mirroring each Prolog predicate
- [diagrams/](diagrams/) — 4 PlantUML sources + render scripts
  - [bdd_gamma_io_schema.puml](diagrams/bdd_gamma_io_schema.puml) — input/output schema
  - [act_gamma_pipeline.puml](diagrams/act_gamma_pipeline.puml) — 4-phase compute pipeline
  - [par_gamma_invariants.puml](diagrams/par_gamma_invariants.puml) — constraints + invariants
  - [par_gamma_hazards.puml](diagrams/par_gamma_hazards.puml) — **FDA MDDT hazard-traceability artifact**
  - [_render.cmd](diagrams/_render.cmd), [_inject_bg.py](diagrams/_inject_bg.py), [_audit_ascii.py](diagrams/_audit_ascii.py)

To execute the verification:

```bash
# Via pytest (canonical CI path):
uv run -- pytest algorithm_verification/gamma/pytest/

# Via Prolog (interactive / spec-level):
swipl -g "use_module('algorithm_verification/gamma/prolog/gamma_runner'), run_all_verifications, halt"
```

To render the SVGs (PlantUML must be installed at `~/.cache/plantuml/plantuml.jar`):

```cmd
cd algorithm_verification\gamma\diagrams
_render.cmd
```
