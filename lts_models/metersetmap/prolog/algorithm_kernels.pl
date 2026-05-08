%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py + sibling modules
%%
%% Numerical algorithm kernels invoked by metersetmap. Each is a pure
%% input -> output function from the LTS's perspective. Their internal
%% correctness is the subject of the QUEUED sibling skill
%% `python-algorithm-verification` (CRUTPr-style; see
%% C:\Users\Derek\.claude\projects\e--github-pymedphys-pymedphys\memory\
%%   project_queued_algorithm_verification_skill.md).
%%
%% Every primitive in this module carries a `%% kernel: see python-algorithm-
%% verification/<name>/` cross-reference. Until the sibling skill lands those
%% references are placeholders (DEFERRED).
%%
%% The metersetmap LTS treats these kernels as opaque transitions. Their
%% inputs and outputs participate in the side-effect-stream label sequence;
%% the kernel bodies do not.

:- module(algorithm_kernels, [
    % ==== MetersetMap kernel ====
    metersetmap_grid/4,                 % metersetmap_grid(+MaxLeafGap, +GridResolution, +LeafPairWidths, -Grid)
    delivery_metersetmap/4,             % delivery_metersetmap(+Delivery, +MaxLeafGap, +GridResolution, +LeafPairWidths, -MetersetMap)
    metersetmap_display/4,              % metersetmap_display(+Grid, +MetersetMap, +Vmin, +Vmax)

    % ==== Gamma kernel ====
    pymedphys_gamma/5,                  % pymedphys_gamma(+RefCoords, +RefDose, +EvalCoords, +EvalDose, +Options, -Gamma)

    % ==== Delivery loaders (5 of them, one per input method) ====
    delivery_from_dicom/3,              % delivery_from_dicom(+DicomPlan, +FractionGroup, -DeliveriesByFraction)
    delivery_from_icom/2,               % delivery_from_icom(+IcomStream, -Delivery)
    delivery_from_monaco/2,             % delivery_from_monaco(+TelPath, -Delivery)
    delivery_from_mosaiq/3,             % delivery_from_mosaiq(+Connection, +FieldId, -Delivery)
    delivery_from_pandas/2,             % delivery_from_pandas(+PandasTable, -Delivery)
                                        %   (TRF-derived delivery)

    % ==== TRF decoder (technically an algorithm; treated as kernel for
    %       boundary-stable reasons -- recomputed from binary via
    %       _trf._read_trf which is cache-decorated)
    trf_split_header_table/3,           % trf_split_header_table(+TrfBytes, -Header, -TableBytes)
    trf_decode_header/2,                % trf_decode_header(+HeaderBytes, -HeaderRecord)
    trf_decode_table/3,                 % trf_decode_table(+TableBytes, +HeaderDataFrame, -TableDataFrame)

    % ==== Image normalisation helper (st_misc.normalize_and_convert_to_uint8) ====
    normalize_to_uint8/4                % normalize_to_uint8(+Array, +Vmin, +Vmax, -Uint8Image)
]).

% ============================================================
% MetersetMap kernel
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:48-52
%%     GRID = pymedphys.metersetmap.grid(
%%         max_leaf_gap=MAX_LEAF_GAP,
%%         grid_resolution=GRID_RESOLUTION,
%%         leaf_pair_widths=LEAF_PAIR_WIDTHS,
%%     )
%% Module-load-time pure function call. The resulting GRID is shared across
%% every invocation of delivery.metersetmap and pymedphys.metersetmap.display.
%% kernel: see python-algorithm-verification/metersetmap/ (DEFERRED)
metersetmap_grid(_MaxLeafGap, _GridResolution, _LeafPairWidths, _Grid) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:342-348
%%     @st.cache_data(hash_funcs={pymedphys.Delivery: hash})
%%     def calculate_metersetmap(delivery):
%%         return delivery.metersetmap(
%%             max_leaf_gap=MAX_LEAF_GAP,
%%             grid_resolution=GRID_RESOLUTION,
%%             leaf_pair_widths=LEAF_PAIR_WIDTHS,
%%         )
%%
%% Per-delivery metersetmap. The wrapping cache (cache_registry.pl entry
%% `calculate_metersetmap`) makes this O(1) on repeated calls with the same
%% Delivery object (hashed via pymedphys.Delivery.hash).
%% kernel: see python-algorithm-verification/metersetmap/ (DEFERRED)
delivery_metersetmap(_Delivery, _MaxLeafGap, _GridResolution, _LeafPairWidths, _MetersetMap) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:307-308, :313-314, :319-320, :325
%%     pymedphys.metersetmap.display(GRID, reference_metersetmap, vmin=0, vmax=largest_metersetmap)
%%     pymedphys.metersetmap.display(GRID, evaluation_metersetmap, ...)
%%     pymedphys.metersetmap.display(GRID, diff, cmap="seismic", ...)
%%     pymedphys.metersetmap.display(GRID, gamma, cmap="coolwarm", ...)
%%
%% Renders into the active matplotlib axis (set by plt.sca prior). Side effect:
%% the figure pixels. Modeled here because it's a numerical-computation render
%% (axis, colormap, and value-mapping decisions are dosimetric).
%% kernel: see python-algorithm-verification/metersetmap/ (DEFERRED)
metersetmap_display(_Grid, _Array, _Vmin, _Vmax) :- fail.

% ============================================================
% Gamma kernel
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:360-370
%%     @st.cache_data
%%     def calculate_gamma(reference_metersetmap, evaluation_metersetmap, gamma_options):
%%         gamma = pymedphys.gamma(
%%             COORDS,
%%             to_tuple(reference_metersetmap),
%%             COORDS,
%%             to_tuple(evaluation_metersetmap),
%%             **gamma_options,
%%         )
%%         return gamma
%%
%% kernel: see python-algorithm-verification/gamma/ (DEFERRED)
%%   The gamma kernel is THE star algorithm for this app. The queued sibling
%%   skill will verify gamma's input/output predicates: value range
%%   (gamma >= 0 with NaN where reference dose below threshold); pass-rate
%%   monotonicity in tolerance; agnew-mcgarry reference benchmarks (the
%%   pymedphys test corpus at lib/pymedphys/tests/gamma/test_agnew_mcgarry.py).
%%
%% Cached: yes (cache_registry.pl entry `calculate_gamma`). The wrapping
%% `to_tuple` conversion at PY:218-220 is a separate cache slot (`to_tuple`)
%% so equal-content arrays hash to the same tuple key.
pymedphys_gamma(_RefCoords, _RefDose, _EvalCoords, _EvalDose, _Options, _Gamma) :- fail.

% ============================================================
% Delivery loaders (one per input method)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:150-152
%%     deliveries_all_fractions = pymedphys.Delivery.from_dicom(
%%         dicom_plan, fraction_group_number="all"
%%     )
%% Returns a dict keyed by fraction-group number; for single-fraction plans
%% the dict has one entry. Multi-fraction plans drive a `radio(select_perscription)`
%% widget (see input_method_stubs.pl for the abstracted transition).
%% raises: AttributeError ("Does not appear to be a photon DICOM plan"),
%%         ValueError (extraction failure -- caught at PY:156-164,
%%                     emits st.warning + st.write(e) + st.stop()).
%% kernel: see python-algorithm-verification/delivery_from_dicom/ (DEFERRED)
delivery_from_dicom(_DicomPlan, _FractionGroup, _DeliveriesByFraction) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:28-30
%%     @st.cache_data()
%%     def delivery_from_icom(icom_stream):
%%         return pymedphys.Delivery.from_icom(icom_stream)
%% Cached: yes (cache_registry.pl `delivery_from_icom`).
%% kernel: see python-algorithm-verification/delivery_from_icom/ (DEFERRED)
delivery_from_icom(_IcomStream, _Delivery) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:33-35
%%     @st.cache_data()
%%     def delivery_from_tel(tel_path):
%%         return pymedphys.Delivery.from_monaco(tel_path)
%% Cached: yes (cache_registry.pl `delivery_from_tel`).
%% kernel: see python-algorithm-verification/delivery_from_monaco/ (DEFERRED)
delivery_from_monaco(_TelPath, _Delivery) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:38-41
%%     @st.cache_data(hash_funcs={pymedphys.mosaiq.Connection: id})
%%     def delivery_from_mosaiq(connection_and_field_id):
%%         connection, field_id = connection_and_field_id
%%         return pymedphys.Delivery.from_mosaiq(connection, field_id)
%%
%% This kernel issues additional Mosaiq SQL queries internally (TxField+
%% delivery-rows JOINs); those table-touching effects are the responsibility
%% of the sibling python-algorithm-verification deliverable but should also
%% be noted here -- the LTS observes the function call, not the inner SQL.
%% Cached: yes (cache_registry.pl `delivery_from_mosaiq`); hash by Connection: id.
%% kernel: see python-algorithm-verification/delivery_from_mosaiq/ (DEFERRED)
%% tables (called transitively): dbo.TxField, dbo.TrackTreatment, dbo.Patient
%%   (read-only; from pymedphys/_mosaiq/delivery.py)
delivery_from_mosaiq(_Connection, _FieldId, _Delivery) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:21-25
%%     @st.cache_data()
%%     def delivery_from_trf(pandas_table):
%%         return pymedphys.Delivery._from_pandas(pandas_table)
%%
%% Note the underscore-prefixed `_from_pandas` -- a private API that takes
%% a decoded TRF table dataframe rather than raw bytes.
%% Cached: yes (cache_registry.pl `delivery_from_trf`).
%% kernel: see python-algorithm-verification/delivery_from_trf/ (DEFERRED)
delivery_from_pandas(_PandasTable, _Delivery) :- fail.

% ============================================================
% TRF decoder (binary -> structured)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:292-294
%%     trf_header_contents, trf_table_contents = _partition.split_into_header_table(trf_contents)
trf_split_header_table(_TrfBytes, _HeaderBytes, _TableBytes) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:296
%%     header = _header.decode_header(trf_header_contents)
trf_decode_header(_HeaderBytes, _HeaderRecord) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:299
%%     table_dataframe = _table.decode_trf_table(trf_table_contents, header_dataframe)
trf_decode_table(_TableBytes, _HeaderDataFrame, _TableDataFrame) :- fail.

% ============================================================
% Image normalisation helper
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:259-277
%%     st_misc.normalize_and_convert_to_uint8(reference_metersetmap, vmin=0, vmax=largest_metersetmap)
%%     st_misc.normalize_and_convert_to_uint8(diff, vmin=-largest_diff, vmax=largest_diff)
%%     st_misc.normalize_and_convert_to_uint8(gamma, vmin=0, vmax=2)
%%
%% Wrapper around an array clip + linear scale to uint8 range. Pure helper.
%% kernel: see python-algorithm-verification/normalize_to_uint8/ (DEFERRED)
normalize_to_uint8(_Array, _Vmin, _Vmax, _Uint8Image) :- fail.
