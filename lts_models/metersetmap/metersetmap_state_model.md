# metersetmap — State Model (orchestration-first)

The metersetmap app ([lib/pymedphys/_streamlit/apps/metersetmap/](../../lib/pymedphys/_streamlit/apps/metersetmap/)) is the pymedphys "gamma application" — a multi-module Streamlit wizard that loads planned + delivered linac data via one of five input methods (DICOM RT Plan, iCOM, TRF logfile, Mosaiq SQL, Monaco tel.1 file), computes a meterset map per delivery, compares the two via gamma analysis, and emits a PNG + PDF report. This document is the **orchestration-first** labeled-transition-system translation: the top-level wizard, output config, calculation pipeline, side-LTS panels (status check + advanced debugging), all caches, all DB queries, and all algorithm-kernel boundaries are at full fidelity. The five input-method sub-LTSs are deferred to a Phase-2 expansion and modeled here as a single `input_method_returned(role, method, results)` event terminal per role per method.

This is the second deliverable produced under the `python-streamlit-state-model` skill, after [pseudonymise](../pseudonymise/pseudonymise_state_model.md). Where pseudonymise was a clean validation of the skill's basic shape (single-page, no DB, no caches, no algorithm-kernel boundary), metersetmap exercises the rest of the surface: the cache tier, the SQL transaction-log analogue from MUZAQ, and the algorithm-kernel cross-reference for gamma.

---

## 1. Primary State Machine

**~17 user-receptive states** (orchestration-first scope; the 5 input-method sub-LTSs each contribute another 5–10 user-receptive states deferred to Phase 2), **12 user event terminals**, **~50 side-effect-stream label families**.

![Primary State Machine](diagrams/stm_primary.svg)

> Source: [`diagrams/stm_primary.puml`](diagrams/stm_primary.puml)

The state machine is a **wizard** with the spine `init → configuring_mode → idle_reference_selecting_method → idle_reference_method_dispatched(M) → idle_evaluation_selecting_method → idle_evaluation_method_dispatched(M) → configuring_output_escan → ready_to_calculate → modal_warning_metersetmap_usage → displaying_results`, plus error and side-LTS branches.

Three load-bearing structural choices, each motivated by Streamlit semantics:

1. **Per-namespace input-method dispatch states** — `idle_reference_method_dispatched(Method)` and `idle_evaluation_method_dispatched(Method)` carry the chosen method as a parameter. This mirrors the Python code's `key_namespace`-prefixed widget keys ([main.py:678-700](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L678-L700)) — Streamlit lets the same widget shape (e.g. `text_input("Patient ID", key=f"{key_namespace}_patient_id")`) coexist for ref + eval columns without state collision. The LTS preserves that.

2. **`modal_warning_metersetmap_usage` is a first-class state**, even though `st.warning(...)` does not pause script execution. The user sees the warning render before the compute spinner appears; bisimulation against a Selenium harness must distinguish "modal rendered, compute starting" from "compute starting silently".

3. **Side-LTS isolation** — `viewing_icom_status`, `viewing_trf_status`, `comparing_baseline_to_output`, and `displaying_baseline_diff` are user-receptive states reachable from the main wizard via sidebar buttons. They mutate `state.sidebar` and `state.main` only; `state.compute` is not touched. The next non-side-LTS event takes the user back to `configuring_mode` or `ready_to_calculate` depending on how far the main wizard had progressed.

**Internal-trace decomposition** of the `click(run_calculation_button) [can_run_calculation]` transition is in [Section 5](#5-compute-pipeline) — 7 internal-trace tiers covering ref/eval metersetmap fold, gamma compute, plot composition, PNG save, and PDF subprocess.

---

## 2. State Dict Schema

### 2.1 Schema diagram

![State Dict Schema](diagrams/bdd_state_dict.svg)

> Source: [`diagrams/bdd_state_dict.puml`](diagrams/bdd_state_dict.puml)

The state{} dict has 8 top-level slots; substantially richer than pseudonymise's. `session{}` is empty (metersetmap uses no `st.session_state`). `caches{}` has **13 slots** (vs pseudonymise's 0). `widgets{}` has 7 top-level fields plus two parallel `input_method_widgets` sub-dicts (`reference` and `evaluation`) with 13 fields each. `compute{}` has 11 slots covering the in-flight pipeline.

**Key insight (orchestration partition):** metersetmap has THREE persistence regimes:

1. **`widgets{}`** — Streamlit-runtime owned; survives every rerun. Mutated only via user widget interactions.
2. **`caches{}`** — `@st.cache_data`-managed; survives until manual `.clear()` or until an arg-key changes. Mutated only via cache miss / cache hit transitions.
3. **`compute{}`** — in-flight pipeline state; **NOT carried across reruns** (re-built from `widgets` + `caches` each time the user clicks Run Calculation). The DCG models the entire compute pipeline as part of the `click(run_calculation_button)` transition body.

`sidebar{}` and `main{}` are pseudo-state (rendered DOM accumulators). The sidebar overview placeholders use `st.empty()` and are **REPLACED** each rerun (PY:60-64); the iCOM/TRF status lines DO accumulate across reruns when the user clicks Check Status repeatedly.

### 2.2 Truncated record details

#### `widgets{}` — Streamlit widget-keyed cache (top-level)

| Field | Type | Anchor | Notes |
|---|---|---|---|
| `config_mode` | `Atom` | [main.py:591](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L591) | `st.sidebar.radio("Config Mode")`; auto-selects first option. |
| `advanced_mode` | `Bool` | [main.py:636](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L636) | Gates: data-method selectbox, png_output_directory text_input, advanced_debugging panel. |
| `status_check_button` | `Bool` (edge) | [main.py:102](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L102) | Triggers iCOM + TRF status scan. |
| `compare_baseline_button` | `Bool` (edge) | [main.py:375](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L375) | Advanced-only; triggers baseline-diff panel. |
| `escan_site` | `Atom` | [main.py:722-728](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L722-L728) | eSCAN PDF report destination. |
| `png_output_directory` | `Atom` | [main.py:746-748](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L746-L748) | Advanced-only text_input; non-advanced uses config default. |
| `run_calculation_button` | `Bool` (edge) | [main.py:764](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L764) | The one that fires the compute pipeline. |
| `reference` | `input_method_widgets{}` | (per-namespace) | Reference-column widget cache. |
| `evaluation` | `input_method_widgets{}` | (per-namespace) | Evaluation-column widget cache. |

#### `input_method_widgets{}` — per-namespace (reference, evaluation)

13 fields covering the union of all 5 input methods' widgets. Most are `_unset` for the input method not currently selected; this mirrors Streamlit's actual behavior (widgets keyed in one rerun's path retain their values even when another path is taken next rerun). See [session_record.pl](prolog/session_record.pl#L80) for the full enumeration with anchors.

#### `caches{}` — 13 `@st.cache_data` slots (the cache tier)

See [cache_registry.pl](prolog/cache_registry.pl) for the full per-slot metadata table. Each slot is one of:
- `_empty` — no entries (initial state)
- `stored(Key, Value)` — one entry, the most recent call's args + result
- `evicted` — manual `.clear()` called (not used in this app)

#### `compute{}` — in-flight pipeline state

| Field | Set by | Notes |
|---|---|---|
| `reference_results` | `input_method_stubs:store_input_method_results/4` | Dict from one of the 5 input methods. None until first ref dispatch. |
| `evaluation_results` | same | None until first eval dispatch. |
| `gamma_options` | `session_record:initial_compute/1` then optionally advanced widgets | Dict with `dose_percent_threshold`, `distance_mm_threshold`, `local_gamma`. See [gamma_options_record.pl](prolog/gamma_options_record.pl). |
| `reference_metersetmap` | `compute_ops:calculate_batch_metersetmap_op/4` | numpy array of the summed ref MU map. None until run_calculation. |
| `evaluation_metersetmap` | same | None until run_calculation. |
| `gamma` | `compute_ops:calculate_gamma_op/2` | numpy array; `pymedphys.gamma` output. None until run_calculation. |
| `fig_handle` | `compute_ops:plot_and_save_results_op/2` | matplotlib Figure. |
| `png_record_directory` | same | `<png_dir>/<patient_id> <ref_id> vs <eval_id>/` |
| `pdf_filepath` | `save_pipeline:convert_png_to_pdf_phase/2` | Set on first attempt; stays set even on PDF fail. |
| `png_filepath` | `save_pipeline:save_png_phase/2` | The matplotlib report PNG. |
| `pdf_success` | same | True on magick or convert success; False if both fail; None pre-pipeline. |

#### `sidebar{}` and `main{}` — UI cascade

| Field | Set by | Notes |
|---|---|---|
| `sidebar.reference_overview` | `render_ops:render_overview_block/6` | Replace-only (not append). PY:60-64 idiom via `st.empty()` placeholder. |
| `sidebar.evaluation_overview` | same | |
| `sidebar.icom_status_lines` | `compute_ops:run_status_check_pipeline/2` | Append-only. Accumulates across multiple Check Status clicks. |
| `sidebar.trf_status_lines` | same | |
| `main.rendered_sections` | every render_ops:* | Ordered list of section atoms; one per top-level `## ...` header. |

### 2.3 State{} write authority

| Top-level field | Written by |
|---|---|
| `tier` | every `step//2` rule, `widget_ops:*`, `compute_ops:*`, `save_pipeline:*`, `input_method_stubs:set_input_method_dispatched_tier/4`, `browse_ops:derive_state/2` |
| `session` | nobody (always `_{}`) |
| `widgets` | `widget_ops:*`, `input_method_stubs:store_input_method_results/4` (only the per-namespace `input_method_widgets` sub-dict, indirectly) |
| `caches` | the cache layer at every cache_miss / cache_hit boundary (see [cache_registry.pl](prolog/cache_registry.pl)) |
| `compute` | `compute_ops:*`, `save_pipeline:*`, `input_method_stubs:store_input_method_results/4` |
| `sidebar` | `render_ops:render_overview_block/6`, `render_ops:render_status_line/3`, `compute_ops:run_status_check_pipeline/2` |
| `main` | every `render_ops:render_*` predicate |
| `rerun_count` | (reserved) |

> **Key insight:** Write authority partitions cleanly by ops-module role: widgets ← Streamlit's runtime via widget_ops; compute ← the compute pipeline (run_calculation transition body); sidebar/main ← rendering acts; caches ← the cache layer. The input-method stubs straddle widgets + compute because they encapsulate a (DEFERRED) sub-LTS that does both.

### 2.4 Enumerations

#### `Tier` — the LTS state-atom enumeration

See [diagrams/bdd_state_dict.puml](diagrams/bdd_state_dict.puml) for the full enumeration. Counts: 11 user-receptive states (orchestration), 3 user-receptive error states, 4 user-receptive side-LTS states, 7 internal-trace states.

### 2.5 Side-Effect Surface

#### 2.5.1 Side-effect pathways

| Mechanism | Module/Function | Direction | Operations | Notes |
|---|---|---|---|---|
| **Streamlit widgets** | `streamlit_boundary:st_radio/4`, `st_checkbox/3`, `st_button/3`, `st_selectbox/4`, `st_text_input/4`, `st_columns/2`, `st_file_uploader/4`, `st_multiselect/5`, `st_pyplot/1`, plus all `st_sidebar_*` variants | user → script | render + value-return | 9 distinct widget families used. |
| **Streamlit page mutation** | `st_write/1`, `st_markdown/2`, `st_warning/1`, `st_text/1` | script → DOM | append-only render | `st_warning` is a first-class modal state per the SKILL.md. |
| **Streamlit sidebar** | `st_sidebar_markdown/1`, `st_sidebar_write/1`, `st_sidebar_empty/1`, `st_placeholder_markdown/2` | script → sidebar DOM | mostly append-only; placeholders are replace | Two `st.empty()` placeholders (ref + eval overview) replaced each rerun. |
| **Streamlit control flow** | `st_stop/0` | script abort | aborts current rerun | Used in DICOM, iCOM, Monaco error paths (DEFERRED in stubs). |
| **DICOM I/O** | `pydicom_dcmread/3` | read | `force=True` permits non-conformant | Used in DICOM file-upload and Monaco-search paths. |
| **iCOM I/O** | `lzma_open_read/2` | read | LZMA-decompress iCOM streams | Used in iCOM and inside cached `delivery_from_icom`. |
| **TRF I/O** | `file_open_read_binary/2` | read | binary TRF logfile | Used in TRF file-upload and INDEXED_TRF_SEARCH paths. |
| **Plotting** | `plt_subplots/4`, `plt_savefig/2`, `imageio_imwrite/2`, `imageio_imread/2`, `algorithm_kernels:metersetmap_display/4`, `algorithm_kernels:normalize_to_uint8/4` | script → image files | plot composition + PNG output | 4 imageio.imwrite + 1 plt.savefig per Run Calculation. |
| **Subprocess (PDF)** | `subprocess_check_call/2` | script → ImageMagick | `magick convert` then fallback `convert` | Both with `shell=True`. |
| **Mosaiq DB** | `mosaiq_boundary:mosaiq_get_cached_connection/2`, `mosaiq_get_username/3`, `mosaiq_get_patient_name/3`, `mosaiq_get_patient_fields/3`, `mosaiq_get_logfile_info/7` | bidirectional SQL | read-only (this app never writes Mosaiq) | The MUZAQ-pattern SQL transaction log. See Section 2.5.2. |
| **Algorithm kernels** | `algorithm_kernels:*` (see Section 2.5.3) | script → numerical libs | pure compute | 11 algorithm-kernel primitives; all DEFERRED. |
| **Cache layer** | per-slot via `@st.cache_data` decorators | script ↔ in-memory cache | hit / miss / store | 13 slots; see Section 2.5.4. |
| **Filesystem** | `path_glob/3`, `path_resolve/2`, `path_mkdir/3`, `path_getmtime/2`, `path_is_file/1` | read | directory scans for status check, Monaco search, indexed TRF search, baseline diff | Heavy use; the status-check sidebar button glob-walks both iCOM and TRF backup directories per linac. |
| **Stdlib** | `datetime_now/1`, `datetime_fromtimestamp/2`, `timeago_format/3`, `base64_b64encode/2`, `sys_platform/1` | pure | non-state-bearing | Used for status-line formatting, PDF download link, platform-specific install URL. |

#### 2.5.2 Tables touched (Mosaiq SQL surface)

This is the **MUZAQ SQL transaction log** for metersetmap. All operations are read-only; metersetmap never writes to the Mosaiq DB.

| Table (schema-qualified) | Database | Access | Operations | Touched by (predicate names) | Anchor |
|---|---|---|---|---|---|
| `dbo.Patient` | MOSAIQ | read-only | `SELECT` (joined to Ident) | `mosaiq_boundary:mosaiq_get_patient_name/3`, `mosaiq_boundary:mosaiq_get_logfile_info/7` | [_mosaiq.py:31](../../lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py#L31), [_trf.py:62-64](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L62-L64) |
| `dbo.Ident` | MOSAIQ | read-only | `SELECT` (`Pat_ID1` lookup) | `mosaiq_boundary:mosaiq_get_patient_name/3`, `mosaiq_boundary:mosaiq_get_patient_fields/3`, `mosaiq_boundary:mosaiq_get_logfile_info/7` | (same) |
| `dbo.TxField` | MOSAIQ | read-only | `SELECT WHERE Pat_Id1 = ?` (filter MU != 0 in Python) | `mosaiq_boundary:mosaiq_get_patient_fields/3`, `algorithm_kernels:delivery_from_mosaiq/3` (transitively) | [_mosaiq.py:26-27](../../lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py#L26-L27) |
| `dbo.TrackTreatment` | MOSAIQ | read-only | `SELECT WHERE delivery_time IN (window)` | `mosaiq_boundary:mosaiq_get_logfile_info/7` (transitively from TRF→Mosaiq join) | [_trf.py:62-64](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L62-L64) |

The exact column names + JOIN structure live in `pymedphys/_mosaiq/helpers.py` and `pymedphys/_trf/manage/index.py` (not modeled in this LTS — they're inside the boundary primitives). All three queries are wrapped by `@st.cache_data` decorators with `Connection: id` hash function, so repeated queries with the same Connection + patient_id (or machine_id + utc_date) hit the cache.

#### 2.5.3 Algorithm kernel boundaries

The full table — every numerical kernel metersetmap calls.

| Kernel | Inputs | Outputs | LTS boundary predicate | Algorithm-verification cross-reference |
|---|---|---|---|---|
| `pymedphys.metersetmap.grid` | `(max_leaf_gap=410, grid_resolution=1, leaf_pair_widths)` | `Grid` dict (`{"jaw": ..., "mlc": ...}`) | `algorithm_kernels:metersetmap_grid/4` | `python-algorithm-verification/metersetmap/` (**DEFERRED**) |
| `delivery.metersetmap` | `(max_leaf_gap, grid_resolution, leaf_pair_widths)` | numpy ndarray (per-control-point MU map summed) | `algorithm_kernels:delivery_metersetmap/5` | `python-algorithm-verification/metersetmap/` (**DEFERRED**) |
| `pymedphys.metersetmap.display` | `(grid, ndarray, vmin, vmax, cmap?)` | mutates active matplotlib axis | `algorithm_kernels:metersetmap_display/4` | `python-algorithm-verification/metersetmap/` (**DEFERRED**) |
| **`pymedphys.gamma`** | `(coords, ref_dose, coords, eval_dose, **gamma_options)` | numpy ndarray (gamma values, NaN where ref-dose < threshold) | `algorithm_kernels:pymedphys_gamma/6` | **`python-algorithm-verification/gamma/` (DEFERRED) — THE star algorithm** |
| `pymedphys.Delivery.from_dicom` | `(dicom_plan, fraction_group="all")` | `dict[fraction → Delivery]` | `algorithm_kernels:delivery_from_dicom/3` | `python-algorithm-verification/delivery_from_dicom/` (**DEFERRED**) |
| `pymedphys.Delivery.from_icom` | `(icom_stream: bytes)` | `Delivery` | `algorithm_kernels:delivery_from_icom/2` | `python-algorithm-verification/delivery_from_icom/` (**DEFERRED**) |
| `pymedphys.Delivery.from_monaco` | `(tel_path: Path)` | `Delivery` | `algorithm_kernels:delivery_from_monaco/2` | `python-algorithm-verification/delivery_from_monaco/` (**DEFERRED**) |
| `pymedphys.Delivery.from_mosaiq` | `(connection, field_id)` | `Delivery` (issues additional Mosaiq SQL queries internally) | `algorithm_kernels:delivery_from_mosaiq/3` | `python-algorithm-verification/delivery_from_mosaiq/` (**DEFERRED**) |
| `pymedphys.Delivery._from_pandas` | `(pandas DataFrame from TRF decode)` | `Delivery` | `algorithm_kernels:delivery_from_pandas/2` | `python-algorithm-verification/delivery_from_trf/` (**DEFERRED**) |
| `_partition.split_into_header_table` | `(trf_bytes)` | `(header_bytes, table_bytes)` | `algorithm_kernels:trf_split_header_table/3` | `python-algorithm-verification/trf_decoder/` (**DEFERRED**) |
| `_header.decode_header` + `_table.decode_trf_table` | TRF binary | `(header DataFrame, table DataFrame)` | `algorithm_kernels:trf_decode_header/2`, `trf_decode_table/3` | `python-algorithm-verification/trf_decoder/` (**DEFERRED**) |
| `st_misc.normalize_and_convert_to_uint8` | `(ndarray, vmin, vmax)` | uint8 image | `algorithm_kernels:normalize_to_uint8/4` | `python-algorithm-verification/normalize_to_uint8/` (**DEFERRED**) |

The gamma kernel is the keystone — its input/output verification is the most safety-critical piece of the queued sibling skill (per the agnew-mcgarry test corpus at `lib/pymedphys/tests/gamma/test_agnew_mcgarry.py`).

#### 2.5.4 Cache surface

13 `@st.cache_data` slots. Full table:

| Slot | Hash function | Wraps | Anchor |
|---|---|---|---|
| `to_tuple` | default (pickle) | nested-tuple coercion of ndarray | [main.py:218-220](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L218-L220) |
| `calculate_metersetmap` | `pymedphys.Delivery: hash` | `delivery.metersetmap(...)` | [main.py:342-348](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L342-L348) |
| `calculate_gamma` | default (pickle on tupled metersetmaps + options) | `pymedphys.gamma(...)` | [main.py:360-370](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L360-L370) |
| `load_dicom_file_if_plan` | `pydicom.FileDataset: pydicom_hash_function` (SOPInstanceUID) | `pydicom.dcmread + SOPClassUID gate` | [_dicom.py:30-36](../../lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py#L30-L36) |
| `load_icom_stream` | default | `lzma.open` | [_icom.py:27-32](../../lib/pymedphys/_streamlit/apps/metersetmap/_icom.py#L27-L32) |
| `get_patient_fields` | `Connection: id` | `msq_helpers.get_patient_fields` | [_mosaiq.py:25-27](../../lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py#L25-L27) |
| `get_patient_name` | `Connection: id` | `msq_helpers.get_patient_name` | [_mosaiq.py:30-32](../../lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py#L30-L32) |
| `delivery_from_trf` | default | `pymedphys.Delivery._from_pandas` | [_deliveries.py:21-25](../../lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py#L21-L25) |
| `delivery_from_icom` | default | `pymedphys.Delivery.from_icom` | [_deliveries.py:28-30](../../lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py#L28-L30) |
| `delivery_from_tel` | default | `pymedphys.Delivery.from_monaco` | [_deliveries.py:33-35](../../lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py#L33-L35) |
| `delivery_from_mosaiq` | `Connection: id` (in tuple) | `pymedphys.Delivery.from_mosaiq` | [_deliveries.py:38-41](../../lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py#L38-L41) |
| `read_trf` | default | TRF binary decode pipeline | [_trf.py:283-301](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L283-L301) |
| `get_mosaiq_configuration` | default | per-(config, headers) Mosaiq topology lookup | [_trf.py:30-38](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L30-L38) |

See [cache_registry.pl](prolog/cache_registry.pl) for the canonical metadata module.

---

## 3. Event → Predicate Transformation Map

(Orchestration-first scope; per-input-method events deferred to Phase 2 expansion. The 5 input-method dispatches collapse to one event terminal `input_method_returned(role, method, results)` per role per method.)

| Event | Guard | Transformation Predicates | State Fields Affected | Side Effects Emitted |
|---|---|---|---|---|
| `init` | `init_state(S0)` | `session_record:initial_state/1` → tier := `configuring_mode` | all dict slots initialised | (widget render only) |
| `select(config_mode, M)` | `user_receptive_state(S0)` | `widget_ops:config_mode_selected/3` → `browse_ops:derive_state/2` | `widgets.config_mode ← M`; tier transitions if from init | `st_sidebar_radio` (Phase 1 of rerun) |
| `toggle(advanced_mode, B)` | same | `widget_ops:advanced_mode_toggled/3` → `derive_state/2` | `widgets.advanced_mode ← B` | `st_sidebar_checkbox` |
| `click(status_check_button)` | same | `widget_ops:status_check_clicked/2` → `compute_ops:run_status_check_pipeline/2` → `derive_state/2` | `widgets.status_check_button ← true` then false; `sidebar.icom_status_lines` and `trf_status_lines` populated | `path_glob` × N linacs × 2 dirs, `path_getmtime` × N files, `datetime_fromtimestamp`, `timeago_format`, `st_sidebar_markdown` × N status lines (or `st_sidebar_write(ConfigMissing)` on KeyError) |
| `click(compare_baseline_button)` | `advanced_mode_active(S0)` AND `user_receptive_state(S0)` | `widget_ops:compare_baseline_clicked/2` → `compute_ops:run_advanced_debugging_pipeline/2` | `widgets.compare_baseline_button ← true` then false; tier transitions through `comparing_baseline_to_output` to `displaying_baseline_diff` (or `error_file_not_found_baseline` mid-loop) | `path_resolve`, `path_glob (rglob)`, `path_is_file`, `imageio_imread` × baseline + eval pair, `np.allclose`, `st_write` × per-file |
| `select(reference_method, M)` | `advanced_mode_active(S0)` AND `user_receptive_state(S0)` | `widget_ops:reference_method_selected/3` | `widgets.reference.data_method ← M`; tier := `idle_reference_method_dispatched(M)` | `st_selectbox` |
| `select(evaluation_method, M)` | same | `widget_ops:evaluation_method_selected/3` | `widgets.evaluation.data_method ← M`; tier := `idle_evaluation_method_dispatched(M)` | `st_selectbox` |
| `input_method_returned(role, method, results)` | `user_receptive_state(S0)`, role ∈ {reference, evaluation}, method ∈ {dicom, icom, trf, mosaiq, monaco} | `input_method_stubs:dispatch_input_method/5` (delegates to per-method stub which calls `store_input_method_results/4` → `render_deliveries_overview/4` → `render_overview_block/6` → `set_input_method_dispatched_tier/4` → `derive_state/2`) | `compute.<role>_results ← results`; `sidebar.<role>_overview` updated | `st_write` (deliveries dataframe + Total MU), `st_placeholder_markdown` (overview block); plus all the (DEFERRED) per-method side effects |
| `select(escan_site, S)` | `user_receptive_state(S0)` | `widget_ops:escan_site_selected/3` → `derive_state/2` | `widgets.escan_site ← S`; tier may transition to `ready_to_calculate` if `can_run_calculation` | (site picker render via `st_misc.get_site_and_directory`) |
| `text_change(png_output_directory, P)` | `advanced_mode_active(S0)` AND `user_receptive_state(S0)` | `widget_ops:png_output_directory_changed/3` | `widgets.png_output_directory ← P` | `st_text_input` |
| `click(run_calculation_button)` (success path) | `can_run_calculation(S0)` | `widget_ops:run_calculation_clicked/2` (clause 1) → tier := `modal_warning_metersetmap_usage` → `compute_ops:run_calculation_pipeline/2` (full 7-phase compute pipeline; see Section 5) | `compute.{reference,evaluation}_metersetmap, gamma, fig_handle, png_record_directory, png_filepath, pdf_filepath, pdf_success` populated; tier ends in `displaying_results` | See Section 5 for full enumeration |
| `click(run_calculation_button)` (PDF-fail path) | same plus subprocess `magick convert` AND `convert` both fail | same dispatch chain, but `save_pipeline:convert_png_to_pdf_phase/2`'s try-chain falls through to `pdf_success := false` → `render_unable_to_create_pdf` | `compute.pdf_success ← false`; tier ends in `error_pdf_conversion` | success-path side effects up through PNG save, then `subprocess_check_call('magick convert ...')` (fail), `subprocess_check_call('convert ...')` (fail), `sys_platform`, `st_write(unable_to_create_pdf)` |
| `click(run_calculation_button)` (no-op path) | `\+ can_run_calculation(S0)` | `widget_ops:run_calculation_clicked/2` (clause 2) | `widgets.run_calculation_button ← false` (edge reset); tier preserved | (none) |

---

## 4. Per-Rerun Pipeline

![Per-Rerun Pipeline](diagrams/act_rerun_pipeline.svg)

> Source: [`diagrams/act_rerun_pipeline.puml`](diagrams/act_rerun_pipeline.puml)

5 phases per rerun: sidebar render → sidebar event dispatch → main-page widget render (data selection + output config + Run button) → main-page event dispatch (input methods + output config) → conditional compute pipeline. The compute pipeline runs only on `click(run_calculation_button) [can_run_calculation]`; otherwise the rerun produces only widget renders + the optional sidebar status / advanced debugging panels.

The reference + evaluation columns are rendered in **parallel** via `st.columns(2)` ([main.py:669](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L669)), but their event dispatch is sequential — `get_input_data_ui("evaluation", **reference_results)` ([main.py:693-700](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L693-L700)) reads `reference_results` to default-fill site/patient_id, so the evaluation column dispatches *after* the reference column in the same rerun.

---

## 5. Compute Pipeline

![Compute Pipeline](diagrams/act_compute_pipeline.svg)

> Source: [`diagrams/act_compute_pipeline.puml`](diagrams/act_compute_pipeline.puml)

The compute pipeline is the body of the `click(run_calculation_button) [can_run_calculation]` transition. Decomposed into 7 internal-trace tiers and 1 modal tier:

0. **`modal_warning_metersetmap_usage`** ([compute_ops.pl:run_calculation_pipeline/2](prolog/compute_ops.pl)) — render warning + section headers. Side effects: `st_write("### MetersetMap usage warning")`, `st_warning(WARNING_MESSAGE)`, `st_write("### Calculation status")`.

1. **`computing_reference_metersetmap`** — fold `delivery.metersetmap(...)` over each ref delivery. Side effects per delivery: `cache_hit(calculate_metersetmap, delivery)` OR (`cache_miss(...)` + `delivery_metersetmap(...)` + `store(...)`). The kernel call's correctness is in the deferred `python-algorithm-verification/metersetmap/` deliverable.

2. **`computing_evaluation_metersetmap`** — same shape on eval deliveries.

3. **`computing_gamma`** — `to_tuple(ref) → to_tuple(eval) → calculate_gamma(...)`. Side effects: 2 `cache_*(to_tuple, ...)` events plus 1 `cache_*(calculate_gamma, ...)`. **The gamma kernel call is the keystone of the metersetmap LTS.**

4. **`computing_plot`** — `plot_and_save_results` body. Side effects: 4 `imageio_imwrite` (reference/evaluation/diff/gamma PNGs), `plt_subplots`, 4 `metersetmap_display` calls, `plot_gamma_hist`. Returns a fig_handle.

5. **(displaying intermediate)** — `st.write("## Results"); st.pyplot(fig)` ([main.py:508-509](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L508-L509)). The fig is now visible to the user.

6. **`computing_png_save`** — `plt.savefig(png_filepath, dpi=100)` plus the "Saved: <path>" status line.

7. **`computing_pdf_convert`** — `subprocess('magick convert ...')` with fallback to `subprocess('convert ...')`. On success: read PDF bytes, base64-encode, emit `st.markdown(href, unsafe_allow_html=True)` download link. On both-fail: render UnableToCreatePDF with platform-specific install URL.

**Translated phases**: 0, 1, 2, 3 partly (the cache lookups are translated, the kernel bodies are boundary primitives), 4, 5, 6, 7 — all in `compute_ops.pl` + `render_ops.pl` + `save_pipeline.pl`.

**Boundary primitives** (the kernel calls inside Phases 1-3): `delivery_metersetmap`, `pymedphys_gamma`, `metersetmap_display`, `normalize_to_uint8` — all in `algorithm_kernels.pl` with `%% kernel:` cross-references to the deferred sibling skill.

---

## 6. Domain Constraints and Invariants

![Constraints and Invariants](diagrams/par_invariants.svg)

> Source: [`diagrams/par_invariants.puml`](diagrams/par_invariants.puml)

### 6.1 Constraints

#### `can_run_calculation_gate`
**Predicate:** `browse_ops:can_run_calculation/1` ⇔ `both_results_present(state) AND output_config_complete(state)`. **Anchor:** [main.py:764](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L764). **Effect on fail:** `click(run_calculation_button)` becomes a no-op via `widget_ops:run_calculation_clicked/2`'s second clause. Tier preserved.

#### `advanced_mode_gate`
**Predicate:** `browse_ops:advanced_mode_active/1` ⇔ `widgets.advanced_mode == true`. **Anchor:** [main.py:636](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L636). Gates 4 events: `select(reference_method, _)`, `select(evaluation_method, _)`, `text_change(png_output_directory, _)`, `click(compare_baseline_button)`. **Effect on fail:** the corresponding widgets are not rendered; the events cannot fire.

#### `valid_dicom_sop_class`
**Predicate:** implicit in [_dicom.py:33, :68](../../lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py#L33). **Anchor:** [_dicom.py:33](../../lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py#L33) (`load_dicom_file_if_plan` returns None for non-plan), [_dicom.py:68-74](../../lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py#L68-L74) (`dicom_input_method` SOPClassUID gate). **Effect on fail:** WrongFileType exception rendered + `return {}`. **DEFERRED** — in stub-build, this gate is not modeled as a tier transition.

#### `no_mosaiq_entries_gate`
**Predicate:** implicit in [_trf.py:_attempt_patient_name_from_mosaiq](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L74). **Anchor:** [_trf.py:102-110](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L102-L110) (catch `_NoMosaiqEntries`). **Effect on fail:** `patient_name := "Unknown"`; `st.warning` rendered. **DEFERRED** — TRF sub-LTS internal.

#### `pdf_conversion_gate`
**Predicate:** `save_pipeline:save_pipeline_outcome/2`. **Anchor:** [main.py:524-535](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L524-L535) (the try/except chain). **Effect on fail:** `tier := error_pdf_conversion`; `render_unable_to_create_pdf` with platform-specific URL.

### 6.2 Invariants

#### `tier_widget_consistency`
`state.tier == ready_to_calculate ⇔ can_run_calculation(state)`. `state.tier == idle_<role>_method_dispatched(M) ⇒ widgets.<role>.data_method == M AND compute.<role>_results != none`. Re-applied by `browse_ops:derive_state/2` after every widget_ops or input_method_stubs predicate.

#### `results_dict_keys`
For each role in {reference, evaluation}: `compute.<role>_results == none OR has keys {site, patient_id, patient_name, data_paths, identifier, deliveries}`. Method-specific extras (selected_icom_deliveries, selected_monaco_plan) also present when applicable. Held by `input_method_stubs:store_input_method_results/4`.

#### `cache_hit_implies_kernel_skipped`
For each cache slot S in cache_registry: `cache_hit(S, K) WHERE caches[S] == stored(K, V)` ⇒ the kernel for S is NOT invoked AND the result V is the same as if the kernel HAD been invoked (assuming kernel determinism). Held by every `@st.cache_data` decorated wrapper at the 13 sites listed in [cache_registry.pl](prolog/cache_registry.pl).

#### `edge_triggered_buttons`
Across two consecutive reruns: each of {`status_check_button`, `compare_baseline_button`, `run_calculation_button`} transitions True → False exactly once between any two click events. Held by `widget_ops:*_clicked` predicates' last clauses (which write False back).

#### `config_invalidates_caches`
`select(config_mode, M)` where M differs from prior_M ⇒ caches that depend on config (path locations, Mosaiq topology, gamma defaults) SHOULD be re-keyed. In practice: `_config.get_config(config_mode)` returns a new dict per call; cache hits depend on dict equality, so a different config_mode naturally produces cache misses for downstream config-keyed lookups. NOT explicitly enforced by the LTS in the orchestration-first build; documented for completeness.

#### `side_lts_isolation`
`state.tier in {viewing_icom_status, viewing_trf_status, comparing_baseline_to_output, displaying_baseline_diff, error_config_missing, error_file_not_found_baseline}` ⇒ `compute.{reference,evaluation}_results, gamma_options, reference_metersetmap, evaluation_metersetmap, gamma` are NOT touched. Held by `compute_ops:run_status_check_pipeline/2` and `run_advanced_debugging_pipeline/2`.

#### `no_session_state_usage`
`state.session == _{}` for every reachable state. Held by every `step//2` rule.

#### `dose_units_preserved`
`reference_metersetmap`, `evaluation_metersetmap` are in MU units (Monitor Units; preserved through the `calculate_metersetmap` + numpy + numpy + ... fold). `gamma` is dimensionless. Held by pymedphys library invariants on `Delivery.metersetmap` and `pymedphys.gamma`; see `python-algorithm-verification/` (DEFERRED).

---

## Source Mapping

(Orchestration-first; per-input-method events deferred.)

| Event | Python Source |
|---|---|
| `init` | [main.py:571](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L571) — `def main()` |
| `select(config_mode, M)` | [main.py:591](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L591) — `st.sidebar.radio("Config Mode", options=config_options)` |
| `toggle(advanced_mode, B)` | [main.py:636](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L636) — `st.sidebar.checkbox("Run in Advanced Mode")` |
| `click(status_check_button)` | [main.py:102](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L102) — `st.sidebar.button("Check status of iCOM and backups")` |
| `click(compare_baseline_button)` | [main.py:375](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L375) — `st.sidebar.button("Compare Baseline to Output Directory")` |
| `select(reference_method, M)` | [main.py:183-187](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L183-L187) — `st.selectbox("Data Input Method", ...)` (reference column instance at :678-684) |
| `select(evaluation_method, M)` | same — evaluation column instance at [main.py:693-700](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L693-L700) |
| `input_method_returned(reference, M, R)` | Synthesised event terminal — collapses the per-method sub-LTSes. Real Python source spans [_dicom.py:39-199](../../lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py#L39), [_icom.py:46-226](../../lib/pymedphys/_streamlit/apps/metersetmap/_icom.py#L46), [_trf.py:128-281](../../lib/pymedphys/_streamlit/apps/metersetmap/_trf.py#L128), [_mosaiq.py:35-98](../../lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py#L35), [_monaco.py:22-88](../../lib/pymedphys/_streamlit/apps/metersetmap/_monaco.py#L22). |
| `input_method_returned(evaluation, M, R)` | same per-method bodies, `key_namespace="evaluation"` |
| `select(escan_site, S)` | [main.py:722-728](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L722-L728) — `st_misc.get_site_and_directory(...)` |
| `text_change(png_output_directory, P)` | [main.py:746-748](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L746-L748) — `st.text_input("png output directory", default)` |
| `click(run_calculation_button)` | [main.py:764](../../lib/pymedphys/_streamlit/apps/metersetmap/main.py#L764) — `st.button("Run Calculation")` |

### Cross-language references

#### Streamlit ↔ algorithm-verification (the keystone pairing)

| Kernel | This LTS boundary predicate | Algorithm-verification deliverable | Status |
|---|---|---|---|
| **`pymedphys.gamma`** | `algorithm_kernels:pymedphys_gamma/6` | **`python-algorithm-verification/gamma/`** | **DEFERRED** — sibling skill not yet built. The kernel is at `lib/pymedphys/_gamma/`. The agnew-mcgarry test corpus at `lib/pymedphys/tests/gamma/test_agnew_mcgarry.py` is the canonical reference dataset for the verification's input/output predicates. |
| `pymedphys.metersetmap.grid` + `delivery.metersetmap` + `pymedphys.metersetmap.display` | `algorithm_kernels:metersetmap_grid/4`, `delivery_metersetmap/5`, `metersetmap_display/4` | `python-algorithm-verification/metersetmap/` | **DEFERRED** |
| `pymedphys.Delivery.from_*` (5 loaders) | `algorithm_kernels:delivery_from_dicom/3` etc. (5 predicates) | `python-algorithm-verification/delivery_from_<method>/` (5 deliverables) | **DEFERRED** |
| `_partition.split_into_header_table` + `_header.decode_header` + `_table.decode_trf_table` | `algorithm_kernels:trf_split_header_table/3` etc. | `python-algorithm-verification/trf_decoder/` | **DEFERRED** |
| `st_misc.normalize_and_convert_to_uint8` | `algorithm_kernels:normalize_to_uint8/4` | `python-algorithm-verification/normalize_to_uint8/` | **DEFERRED** |

This is the intended cross-reference structure: the LTS observes the kernel call, the algorithm-verification deliverable verifies the kernel's input-output correctness. Together they constitute a Milner-bisimulation-respecting decomposition of metersetmap's full operational semantics.

#### Streamlit ↔ legacy clinical-system equivalents

**Pairing pending.** MOSAIQ has its own QA workflows for treatment delivery comparison, but they're internal to MOSAIQ's clinical-management surface and not directly equivalent to metersetmap's gamma-based comparison of planned vs delivered MU maps. A precise pairing would target a specific MOSAIQ form (likely a Field-level audit form) and document the bisimulation relation. Document absence: no counterpart deliverable exists yet; pairing pending.

#### Operational equivalence statement (sketch)

For input sequence:
```
[ init,
  select(config_mode, production),
  input_method_returned(reference, dicom, ref_results),
  input_method_returned(evaluation, icom, eval_results),
  select(escan_site, "default_site"),
  click(run_calculation_button) ]
```
where `ref_results` is a valid DICOM RT Plan deliveries dict and `eval_results` is a valid iCOM deliveries dict for the same patient: this LTS reaches `displaying_results` with:

- `widgets.config_mode == production`
- `compute.reference_results == ref_results`, `compute.evaluation_results == eval_results`
- `compute.reference_metersetmap` populated (numpy ndarray)
- `compute.evaluation_metersetmap` populated
- `compute.gamma` populated
- `compute.fig_handle` populated; `compute.png_filepath` and `compute.pdf_filepath` set
- `compute.pdf_success == true` (assuming ImageMagick installed)
- `sidebar.reference_overview` and `sidebar.evaluation_overview` populated with patient/MU blocks
- `main.rendered_sections` includes intro, data_selection, output_locations, calculation_header, warning_modal_rendered, status(...), results_rendered, save_status(...), pdf_download_link(...)
- `tier == displaying_results`

with the side-effect-stream label sequence:
```
[ st_sidebar_radio(config_mode), st_sidebar_checkbox(advanced_mode),
  st_sidebar_button(status_check), st_sidebar_button(compare_baseline),
  st_sidebar_empty x 2 (overview placeholders),
  st_columns(2),
  (DEFERRED dicom_input_method side-effects: pydicom_dcmread, SOPClassUID gate,
   delivery_from_dicom, st_write x several)
  st_placeholder_markdown(reference_overview),
  st_write(deliveries_dataframe), st_write(total_mu_line),
  (DEFERRED icom_input_method side-effects: path_glob, lzma_open_read x N
   (cache miss), delivery_from_icom x N (cache miss), st_multiselect, st_write)
  st_placeholder_markdown(evaluation_overview),
  st_write(deliveries_dataframe), st_write(total_mu_line),
  st_misc.get_site_and_directory(escan_site),
  st_button(run_calculation),
  -- click triggers:
  st_write("### MetersetMap usage warning"), st_warning(WARNING_MESSAGE),
  st_write("### Calculation status"),
  st_write("Calculating Reference MetersetMap..."),
  cache_miss(calculate_metersetmap, ref_delivery_0), delivery_metersetmap(...),
  st_write("Calculating Evaluation MetersetMap..."),
  cache_miss(calculate_metersetmap, eval_delivery_0), delivery_metersetmap(...),
  st_write("Calculating Gamma..."),
  cache_miss(to_tuple, ref_msm_array),
  cache_miss(to_tuple, eval_msm_array),
  cache_miss(calculate_gamma, args), pymedphys_gamma(coords, ref_tup, coords, eval_tup, opts),
  st_write("Creating figure..."),
  imageio_imwrite x 4, plt_subplots, metersetmap_display x 4, plot_gamma_hist,
  st_write("## Results"), st_pyplot(fig),
  st_write("## Saving reports"), st_write("### PNG"),
  st_write("Saving figure as PNG..."), plt_savefig(png_filepath, 100),
  st_write("Saved: ..."),
  st_write("### PDF"), st_write("Converting PNG to PDF..."),
  subprocess_check_call(magick_cmd) (success),
  file_open_read_binary(pdf_filepath), base64_b64encode,
  st_markdown(<a href="data:file/zip;base64,...">) ]
```

Caveats: the algorithm-verification deliverables for `delivery_metersetmap`, `pymedphys_gamma`, and the 5 delivery loaders are deferred, so the LTS treats them as pure functions with whatever output the kernels produce. If those kernels have side effects beyond returning the documented values (e.g. logging, cache mutation, additional SQL queries from `delivery_from_mosaiq`), the bisimulation will differ at the side-effect-stream level. Per [_deliveries.py:38-41](../../lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py#L38-L41), `delivery_from_mosaiq` IS known to issue additional SQL queries internally — those table-touching effects are responsibility of the sibling python-algorithm-verification deliverable.

---

## Files

- [prolog/](prolog/) — 12 Prolog modules
  - **Boundary** (3): [streamlit_boundary.pl](prolog/streamlit_boundary.pl), [mosaiq_boundary.pl](prolog/mosaiq_boundary.pl), [algorithm_kernels.pl](prolog/algorithm_kernels.pl)
  - **Records / registry** (3): [session_record.pl](prolog/session_record.pl), [gamma_options_record.pl](prolog/gamma_options_record.pl), [cache_registry.pl](prolog/cache_registry.pl)
  - **Ops** (5): [browse_ops.pl](prolog/browse_ops.pl), [widget_ops.pl](prolog/widget_ops.pl), [compute_ops.pl](prolog/compute_ops.pl), [render_ops.pl](prolog/render_ops.pl), [save_pipeline.pl](prolog/save_pipeline.pl)
  - **Stubs** (1): [input_method_stubs.pl](prolog/input_method_stubs.pl) — collapses the 5 input-method sub-LTSes into a single `dispatch_input_method/5` predicate. Phase-2 expansion: split into `dicom_phase_ops.pl`, `icom_phase_ops.pl`, `trf_phase_ops.pl`, `mosaiq_phase_ops.pl`, `monaco_phase_ops.pl`, each with its own internal-state alphabet.
  - **DCG** (1): [ui_state_dcg.pl](prolog/ui_state_dcg.pl)
- [diagrams/](diagrams/) — 5 PlantUML sources + render scripts
  - [stm_primary.puml](diagrams/stm_primary.puml), [bdd_state_dict.puml](diagrams/bdd_state_dict.puml), [act_rerun_pipeline.puml](diagrams/act_rerun_pipeline.puml), [act_compute_pipeline.puml](diagrams/act_compute_pipeline.puml), [par_invariants.puml](diagrams/par_invariants.puml)
  - [_render.cmd](diagrams/_render.cmd), [_inject_bg.py](diagrams/_inject_bg.py), [_audit_ascii.py](diagrams/_audit_ascii.py)

To render the SVGs (PlantUML must be installed; see _render.cmd header):

```cmd
cd lts_models\metersetmap\diagrams
_render.cmd
```

---

## Phase-2 expansion: input-method sub-LTSs

When the deferred Phase 2 happens, replace [input_method_stubs.pl](prolog/input_method_stubs.pl) with 5 dedicated phase modules:

- `dicom_phase_ops.pl` — FILE_UPLOAD vs MONACO_SEARCH radio, SOPClassUID gate (3 distinct error_wrong_dicom_type tiers), Monaco-search file-system glob, fraction-group selector, `error_dicom_extraction_value` (Delivery.from_dicom ValueError → `st.warning + st.stop`)
- `icom_phase_ops.pl` — patient_id text input (advanced), per-directory glob, multiselect, error_input_required (`st.stop`), per-stream `load_icom_stream` cache loop, per-stream `delivery_from_icom` cache loop
- `trf_phase_ops.pl` — FILE_UPLOAD vs INDEXED_TRF_SEARCH radio, multiselect, `_read_trf` cache loop, **the Mosaiq patient-name lookup sub-pipeline** (calls `mosaiq_get_logfile_info`), `error_unknown_patient` (`NoMosaiqEntries` → `st.warning`)
- `mosaiq_phase_ops.pl` — site picker, `mosaiq_get_username` boundary, patient_id text input, `mosaiq_get_cached_connection` cache_resource boundary, `mosaiq_get_patient_name` + `mosaiq_get_patient_fields` cache_data boundaries, field_id multiselect, per-field-id `delivery_from_mosaiq` cache loop
- `monaco_phase_ops.pl` — delegates to `st_monaco.monaco_tel_files_picker` (utilities/monaco.py — its own sub-LTS), `error_no_control_points` (`NoControlPointsFound` → renders, no `st.stop`)

Each phase module would add ~5–10 user-receptive states and ~5–10 event terminals to the alphabet, expanding the primary STM diagram with composite states for each method. Estimated Phase-2 artifact size: ~3000-4000 additional lines (Prolog + diagrams + appendix to this markdown).
