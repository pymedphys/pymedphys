%% Source: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py
%%        + lib/pymedphys/_streamlit/apps/metersetmap/_trf.py
%%        + lib/pymedphys/_streamlit/utilities/mosaiq.py
%%
%% Mosaiq DB boundary primitives -- the SQL transaction-log entries from the
%% MUZAQ pattern. Every persistence call to the Mosaiq SQL Server appears
%% here with a `%% tables:` annotation naming the underlying table(s) and
%% the operation kind (read-only for this app -- metersetmap never writes
%% to Mosaiq, only reads patient + delivery + logfile-correlation rows).
%%
%% This is the canonical analogue of cs-ui-state-model's `clarion_boundary.pl`
%% PM/DAL section -- MOSAIQ is the same SQL Server database, accessed here via
%% pymssql + pymedphys SQLAlchemy helpers rather than IdeaBlade EntityManager.

:- module(mosaiq_boundary, [
    % ==== Connection management ====
    mosaiq_get_cached_connection/2,     % mosaiq_get_cached_connection(+Server, -Connection)
    mosaiq_get_username/3,              % mosaiq_get_username(+Hostname, +Port, -SqlUser)

    % ==== Patient queries ====
    mosaiq_get_patient_name/3,          % mosaiq_get_patient_name(+Connection, +PatientId, -PatientName)
    mosaiq_get_patient_fields/3,        % mosaiq_get_patient_fields(+Connection, +PatientId, -PatientFieldsDataFrame)

    % ==== TRF -> Mosaiq logfile correlation ====
    mosaiq_get_logfile_info/7           % mosaiq_get_logfile_info(+Connection, +MachineId, +UtcDate,
                                        %                        +Timezone, +FieldLabel, +FieldName, -Details)
]).

% ============================================================
% Connection management
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:56
%%     connection = st_mosaiq.get_cached_mosaiq_connection(**server)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:47-48
%%     connections = {server["alias"]: st_mosaiq.get_cached_mosaiq_connection(**server) ...}
%%
%% This is itself an @st.cache_resource boundary (see cache_registry.pl); the
%% Connection object is a pymedphys.mosaiq.Connection wrapping a pymssql cursor.
%% Every subsequent query reuses the cached Connection.
%% tables: (no read; opens a session)
mosaiq_get_cached_connection(_Server, _Connection) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:46-48
%%     sql_user = _pp_msq_credentials.get_username(hostname=server["hostname"], port=server["port"])
%% Reads the cached SQL credential for the (hostname, port) pair. Pure lookup;
%% the username is rendered to the page at PY:49.
mosaiq_get_username(_Hostname, _Port, _SqlUser) :- fail.

% ============================================================
% Patient queries (read-only)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:30-32
%%     @st.cache_data(hash_funcs={pymedphys.mosaiq.Connection: id})
%%     def get_patient_name(connection, patient_id):
%%         return msq_helpers.get_patient_name(connection, patient_id)
%%
%% tables: dbo.Patient (SELECT) JOIN dbo.Ident (SELECT)
%%   Reads the patient's last/first name pair keyed by Pat_ID1 (the human
%%   patient identifier; Mosaiq's primary key is the surrogate Pat_Id1 numeric
%%   column on dbo.Patient). See pymedphys/_mosaiq/helpers.py for the SELECT.
%%
%% Cached: yes (cache_registry.pl entry `get_patient_name`); hash by Connection: id.
mosaiq_get_patient_name(_Connection, _PatientId, _PatientName) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:25-27
%%     @st.cache_data(hash_funcs={pymedphys.mosaiq.Connection: id})
%%     def get_patient_fields(connection, patient_id):
%%         return msq_helpers.get_patient_fields(connection, patient_id)
%%
%% tables: dbo.TxField (SELECT) JOIN dbo.Patient (SELECT) JOIN dbo.Ident (SELECT)
%%         additional treatment-record joins per msq_helpers.get_patient_fields
%%
%% Returns a pandas DataFrame with columns including:
%%   - field_id    (the Mosaiq surrogate field key)
%%   - field_label (display label)
%%   - field_name  (display name)
%%   - monitor_units
%% The orchestration filters out rows with monitor_units == 0 at PY:73.
%%
%% Cached: yes (cache_registry.pl entry `get_patient_fields`); hash by Connection: id.
mosaiq_get_patient_fields(_Connection, _PatientId, _PatientFieldsDataFrame) :- fail.

% ============================================================
% TRF -> Mosaiq logfile correlation
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:62-64
%%     current_details = pmp_index.get_logfile_mosaiq_info(
%%         connection, machine_id, utc_date, mosaiq_timezone, field_label, field_name
%%     )
%%
%% tables: dbo.TxField (SELECT WHERE machine_id, time-of-delivery in window),
%%         dbo.Patient (SELECT JOIN), dbo.Ident (SELECT JOIN),
%%         dbo.TrackTreatment (SELECT WHERE delivery_time in window)
%%   See pymedphys/_trf/manage/index.py for the precise SELECT. The
%%   correlation joins by machine_id + delivery time-window converted from
%%   the Mosaiq site's timezone.
%%
%% raises: pymedphys._mosaiq.delivery.NoMosaiqEntries when no row matches.
%% Caught at _trf.py:102-107 -- patient_name set to "Unknown" + st.warning.
%%
%% Cached: NO (called inside an @st.cache_data wrapper at the orchestration
%% level via _trf._get_mosaiq_configuration, but this primitive itself is
%% recomputed per (machine_id, utc_date, ...) tuple).
mosaiq_get_logfile_info(_Connection, _MachineId, _UtcDate,
                        _Timezone, _FieldLabel, _FieldName, _Details) :- fail.
