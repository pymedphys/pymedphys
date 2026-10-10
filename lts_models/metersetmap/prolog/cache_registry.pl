%% Source: lib/pymedphys/_streamlit/apps/metersetmap/  (13 @st.cache_data sites)
%%
%% Registry of all `@st.cache_data` slots in the metersetmap app. Each slot
%% has its own state in `state.caches[Slot]` -- one of:
%%   _empty                      % no entries
%%   stored(Key, Value)          % one entry (most common; cache_data caches
%%                               % the result of the most recent call)
%%   evicted                     % manual .clear() called (not used in this app)
%%
%% Hash function determines what counts as a cache key; per the SKILL.md
%% the cache primitives emit `cache_miss(fn, args)` and `cache_hit(fn, args)`
%% labels. The first call after Streamlit startup OR after a relevant input
%% change is a miss -> compute; subsequent calls with the same key are hits.
%%
%% This module declares the slot list and gives a per-slot record of:
%%   - where the cache decoration lives in the source
%%   - the hash function (default = pickle-based, or custom hash_funcs)
%%   - the kernel boundary the cache wraps
%%   - any TTL or invalidation triggers
%%
%% Streamlit's @st.cache_data documentation:
%%   <https://docs.streamlit.io/library/api-reference/performance/st.cache_data>
%% Key semantics: the cache is keyed by the input args' pickled bytes (default)
%% or by the supplied hash_func mapping. TTL is None by default (cache lives
%% for the entire Streamlit session). Manual invalidation via fn.clear() or
%% st.cache_data.clear().

:- module(cache_registry, [
    initial_caches/1,               % initial_caches(-CachesDict)
    cache_slot_metadata/3,          % cache_slot_metadata(+SlotName, -HashFunc, -KernelBoundary)
    all_cache_slots/1               % all_cache_slots(-Slots)
]).

%% Initial cache state -- every slot is _empty until first invocation.
initial_caches(_{
    to_tuple:                _empty,
    calculate_metersetmap:   _empty,
    calculate_gamma:         _empty,
    load_dicom_file_if_plan: _empty,
    load_icom_stream:        _empty,
    get_patient_fields:      _empty,
    get_patient_name:        _empty,
    delivery_from_trf:       _empty,
    delivery_from_icom:      _empty,
    delivery_from_tel:       _empty,
    delivery_from_mosaiq:    _empty,
    read_trf:                _empty,
    get_mosaiq_configuration:_empty
}).

all_cache_slots([
    to_tuple,
    calculate_metersetmap,
    calculate_gamma,
    load_dicom_file_if_plan,
    load_icom_stream,
    get_patient_fields,
    get_patient_name,
    delivery_from_trf,
    delivery_from_icom,
    delivery_from_tel,
    delivery_from_mosaiq,
    read_trf,
    get_mosaiq_configuration
]).

% ============================================================
% Per-slot metadata
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:218-220
%%     @st.cache_data
%%     def to_tuple(array):
%%         return tuple(map(tuple, array))
%% Generic ndarray -> nested-tuple conversion. Used to make numpy arrays
%% hashable for the calculate_gamma cache (numpy arrays don't hash on identity).
cache_slot_metadata(to_tuple,
    'default (pickle-based)',
    'pure helper: array -> nested tuple').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:342-348
%%     @st.cache_data(hash_funcs={pymedphys.Delivery: hash})
%%     def calculate_metersetmap(delivery):
%%         return delivery.metersetmap(...)
%% Hash uses pymedphys.Delivery.__hash__ (custom). Per-delivery cache;
%% repeated calls with the same Delivery object hit.
cache_slot_metadata(calculate_metersetmap,
    'pymedphys.Delivery: hash (custom __hash__ on Delivery)',
    'algorithm_kernels:delivery_metersetmap/5').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:360-370
%%     @st.cache_data
%%     def calculate_gamma(reference_metersetmap, evaluation_metersetmap, gamma_options):
%%         return pymedphys.gamma(...)
%% Default hash; arrays are converted to tuples via to_tuple before being
%% passed in (PY:364, :366), so the args are pickle-stable.
cache_slot_metadata(calculate_gamma,
    'default (pickle on tupled metersetmaps + options dict)',
    'algorithm_kernels:pymedphys_gamma/6').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:30-36
%%     @st.cache_data(hash_funcs={pydicom.dataset.FileDataset: pydicom_hash_function})
%%     def load_dicom_file_if_plan(filepath):
%%         dcm = pydicom.dcmread(str(filepath), force=True, stop_before_pixels=True)
%%         if dcm.SOPClassUID == DICOM_PLAN_UID: return dcm
%%         return None
%% Custom hash function: SOPInstanceUID. Wraps pydicom.dcmread + the SOPClassUID
%% gate. Returns None if not a plan -- those Nones ARE cached, so a non-plan
%% file scanned once won't be re-read. Used in the MONACO_SEARCH path of
%% _dicom.py (file-system scan).
cache_slot_metadata(load_dicom_file_if_plan,
    'pydicom.dataset.FileDataset: pydicom_hash_function (SOPInstanceUID)',
    'streamlit_boundary:pydicom_dcmread/3 + SOPClassUID gate').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:27-32
%%     @st.cache_data
%%     def load_icom_stream(icom_path):
%%         with lzma.open(icom_path, "r") as f:
%%             contents = f.read()
%%         return contents
%% Default hash on the path-like argument.
cache_slot_metadata(load_icom_stream,
    'default (pickle on PosixPath)',
    'streamlit_boundary:lzma_open_read/2').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:25-27
%%     @st.cache_data(hash_funcs={pymedphys.mosaiq.Connection: id})
%%     def get_patient_fields(connection, patient_id):
%%         return msq_helpers.get_patient_fields(connection, patient_id)
%% Connection: id means cache by Python object identity of the Connection.
%% That's stable so long as `st_mosaiq.get_cached_mosaiq_connection` returns
%% the same object (it does -- it's @st.cache_resource decorated).
cache_slot_metadata(get_patient_fields,
    'pymedphys.mosaiq.Connection: id + patient_id default',
    'mosaiq_boundary:mosaiq_get_patient_fields/3').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:30-32
cache_slot_metadata(get_patient_name,
    'pymedphys.mosaiq.Connection: id + patient_id default',
    'mosaiq_boundary:mosaiq_get_patient_name/3').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:21-25
cache_slot_metadata(delivery_from_trf,
    'default (pickle on pandas DataFrame)',
    'algorithm_kernels:delivery_from_pandas/2').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:28-30
cache_slot_metadata(delivery_from_icom,
    'default (pickle on bytes)',
    'algorithm_kernels:delivery_from_icom/2').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:33-35
cache_slot_metadata(delivery_from_tel,
    'default (pickle on PosixPath)',
    'algorithm_kernels:delivery_from_monaco/2').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_deliveries.py:38-41
%% Note: takes a (Connection, field_id) TUPLE, not separate args. The hash_func
%% maps Connection: id; field_id uses default. Tuple element ordering matters.
cache_slot_metadata(delivery_from_mosaiq,
    'pymedphys.mosaiq.Connection: id (in tuple) + field_id default',
    'algorithm_kernels:delivery_from_mosaiq/3').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:283-301
%%     @st.cache_data()
%%     def _read_trf(path_or_binary):
%%         ... seek(0); read(); split + decode header + decode table
%% Wraps the entire TRF binary -> (header_df, table_df) decode.
cache_slot_metadata(read_trf,
    'default (pickle on path or binary buffer)',
    'algorithm_kernels:trf_split_header_table/3 + trf_decode_header/2 + trf_decode_table/3').

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:30-38
%%     @st.cache_data
%%     def _get_mosaiq_configuration(config, headers):
%%         machine_centre_map = _config.get_machine_centre_map(config)
%%         mosaiq_details = _config.get_mosaiq_details(config)
%%         centres = {machine_centre_map[machine_id] for machine_id in headers["machine"]}
%%         mosaiq_servers = [mosaiq_details[centre]["server"] for centre in centres]
%%         return machine_centre_map, mosaiq_details, mosaiq_servers
%% Caches the per-(config, header set) Mosaiq topology lookup.
cache_slot_metadata(get_mosaiq_configuration,
    'default (pickle on config dict + headers DataFrame)',
    'pure compute: config -> Mosaiq server topology').
