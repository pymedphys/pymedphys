%% Source: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py + _icom.py + _trf.py
%%        + _mosaiq.py + _monaco.py
%%
%% STUB MODULE for the 5 input-method sub-LTSs.
%%
%% In the orchestration-first build, each input method's internal state machine
%% (file-upload vs server-search radios, patient-id text input, multiselect
%% behavior, error handling, fraction-group selection, etc.) is COLLAPSED to
%% a single transition `<method>_phase_returned(Role, Results)` that takes
%% the per-method results dict (the dict returned by `<method>_input_method`
%% in the source) and stores it into `state.compute.<role>_results`.
%%
%% A full Phase-2 expansion of this module would split each stub into its
%% own `<method>_phase_ops.pl` file with the per-widget transitions, errors,
%% and cache interactions modeled at full fidelity. Until then:
%%   - state.widgets.<role>.<method>_*  is set to opaque _stubbed atom values
%%     when this stub fires
%%   - the side-effect-stream label `<method>_input_method_called(Role, ResultsKeys)`
%%     stands in for the per-widget render labels
%%   - error states are NOT exercised through these stubs; they would surface
%%     when the per-method modules are expanded
%%
%% The orchestration LTS DOES correctly handle the *output* contract: each
%% stub's results dict has the keys (site, patient_id, patient_name,
%% data_paths, identifier, deliveries) plus method-specific extras
%% (selected_icom_deliveries for iCOM, selected_monaco_plan for Monaco).
%% These keys are read by widget_ops + compute_ops + render_ops correctly.

:- module(input_method_stubs, [
    dicom_phase_returned/4,             % dicom_phase_returned(+Role, +Results, +State0, -State)
    icom_phase_returned/4,              % icom_phase_returned(+Role, +Results, +State0, -State)
    trf_phase_returned/4,               % trf_phase_returned(+Role, +Results, +State0, -State)
    mosaiq_phase_returned/4,            % mosaiq_phase_returned(+Role, +Results, +State0, -State)
    monaco_phase_returned/4,            % monaco_phase_returned(+Role, +Results, +State0, -State)

    dispatch_input_method/4             % dispatch_input_method(+Role, +Method, +Results, +State0, -State)
]).

:- use_module(browse_ops, [derive_state/2]).
:- use_module(render_ops, [render_overview_block/6, render_deliveries_overview/4]).

% ============================================================
% DICOM stub
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:39-199 (dicom_input_method)
%%
%% Sub-LTS NOT modeled here (DEFERRED). Internal states would include:
%%   idle_dicom_method_choice         (FILE_UPLOAD | MONACO_SEARCH radio)
%%   idle_dicom_file_upload           (st.file_uploader)
%%   validating_dicom_sop_class        (SOPClassUID gate)
%%   error_wrong_dicom_type            (3 distinct messages: not DICOM, not RT Plan, not photon)
%%   idle_dicom_monaco_search          (site picker, patient_id text input)
%%   error_no_records_found_dicom
%%   idle_select_monaco_export_plan    (radio over found .dcm files)
%%   idle_dicom_perscription_chooser   (multi-fraction radio)
%%   error_dicom_extraction_value      (Delivery.from_dicom ValueError -> st.warning + st.stop)
%%
%% Stub: takes a fully-formed results dict and stores it.
%% Expected results keys: site, patient_id, patient_name, data_paths,
%%                        identifier, deliveries
dicom_phase_returned(Role, Results, S0, S) :-
    store_input_method_results(Role, Results, S0, S1),
    %% Set the appropriate per-method-dispatched tier.
    set_input_method_dispatched_tier(Role, dicom, S1, S2),
    derive_state(S2, S).

% ============================================================
% iCOM stub
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:46-226 (icom_input_method)
%%
%% Sub-LTS NOT modeled here (DEFERRED). Internal states would include:
%%   idle_icom_patient_id              (text_input, advanced-mode-only)
%%   computing_icom_path_glob          (per-directory pathlib glob -> deliveries list)
%%   error_no_records_found_icom
%%   idle_icom_multiselect             (timestamps multiselect)
%%   computing_load_icom_streams       (per-path load_icom_stream cache hit/miss)
%%   computing_delivery_from_icom_loop (per-stream delivery_from_icom kernel call)
%%   error_input_required              (no timestamps selected -> st.stop)
%%
%% Stub: same shape as dicom.
%% Expected results keys: site (None), patient_id, patient_name,
%%                        selected_icom_deliveries, data_paths, identifier, deliveries
icom_phase_returned(Role, Results, S0, S) :-
    store_input_method_results(Role, Results, S0, S1),
    set_input_method_dispatched_tier(Role, icom, S1, S2),
    derive_state(S2, S).

% ============================================================
% TRF stub
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:128-301 (trf_input_method)
%%
%% Sub-LTS NOT modeled here (DEFERRED). Internal states would include:
%%   idle_trf_method_choice            (FILE_UPLOAD | INDEXED_TRF_SEARCH radio)
%%   idle_trf_file_upload              (file_uploader, accept_multiple_files=True)
%%   error_config_missing_trf
%%   idle_trf_indexed_search           (patient_id text_input, then multiselect)
%%   error_no_records_found_trf
%%   computing_read_trf_loop           (per-file _read_trf cache hit/miss)
%%   computing_attempt_patient_name_from_mosaiq  (sub-pipeline)
%%   error_unknown_patient             (NoMosaiqEntries -> st.warning, "Unknown")
%%   computing_delivery_from_trf_loop  (per-table delivery_from_pandas cache hit/miss)
%%
%% Stub.
%% Expected results keys: site (None), patient_id, patient_name, data_paths,
%%                        identifier, deliveries
trf_phase_returned(Role, Results, S0, S) :-
    store_input_method_results(Role, Results, S0, S1),
    set_input_method_dispatched_tier(Role, trf, S1, S2),
    derive_state(S2, S).

% ============================================================
% Mosaiq stub
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:35-98 (mosaiq_input_method)
%%
%% Sub-LTS NOT modeled here (DEFERRED). Internal states would include:
%%   idle_mosaiq_site_picker
%%   computing_mosaiq_get_username     (boundary: mosaiq_get_username)
%%   idle_mosaiq_patient_id            (text_input)
%%   computing_mosaiq_get_connection   (cache_resource: connection)
%%   computing_get_patient_name        (cache_data; mosaiq_boundary:mosaiq_get_patient_name)
%%   computing_get_patient_fields      (cache_data; mosaiq_boundary:mosaiq_get_patient_fields)
%%   idle_mosaiq_field_id_multiselect
%%   computing_delivery_from_mosaiq_loop (per-field-id delivery_from_mosaiq kernel)
%%
%% Stub.
%% Expected results keys: site, patient_id, patient_name, data_paths (empty),
%%                        identifier, deliveries
mosaiq_phase_returned(Role, Results, S0, S) :-
    store_input_method_results(Role, Results, S0, S1),
    set_input_method_dispatched_tier(Role, mosaiq, S1, S2),
    derive_state(S2, S).

% ============================================================
% Monaco stub
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_monaco.py:22-88 (monaco_input_method)
%%
%% Sub-LTS NOT modeled here (DEFERRED). The Monaco method delegates much of
%% its widget shape to st_monaco.monaco_tel_files_picker (in
%% _streamlit/utilities/monaco.py). Internal states would include:
%%   idle_monaco_tel_files_picker      (delegated; site + plan picker)
%%   error_picker_keyerror             (KeyError on missing keys -> st.stop)
%%   computing_delivery_from_tel_loop  (per-tel-path delivery_from_monaco kernel)
%%   error_no_control_points           (empty deliveries[0].mu -> NoControlPointsFound)
%%
%% Stub.
%% Expected results keys: site, patient_id, patient_name, selected_monaco_plan,
%%                        data_paths, identifier, deliveries
monaco_phase_returned(Role, Results, S0, S) :-
    store_input_method_results(Role, Results, S0, S1),
    set_input_method_dispatched_tier(Role, monaco, S1, S2),
    derive_state(S2, S).

% ============================================================
% Dispatch helper (single entry point, used by ui_state_dcg.pl)
% ============================================================

dispatch_input_method(Role, dicom, Results, S0, S) :- dicom_phase_returned(Role, Results, S0, S).
dispatch_input_method(Role, icom,  Results, S0, S) :- icom_phase_returned(Role, Results, S0, S).
dispatch_input_method(Role, trf,   Results, S0, S) :- trf_phase_returned(Role, Results, S0, S).
dispatch_input_method(Role, mosaiq, Results, S0, S) :- mosaiq_phase_returned(Role, Results, S0, S).
dispatch_input_method(Role, monaco, Results, S0, S) :- monaco_phase_returned(Role, Results, S0, S).

% ============================================================
% Internal helpers
% ============================================================

%% Store the per-role input-method results in state.compute.<role>_results,
%% then update the sidebar overview block + render the per-role deliveries
%% table on the main page.
store_input_method_results(Role, Results, S0, S) :-
    %% Slot the results dict into compute.<role>_results
    Compute0 = S0.compute,
    (   Role == reference
    ->  Compute1 = Compute0.put(reference_results, Results)
    ;   Compute1 = Compute0.put(evaluation_results, Results)
    ),
    S1 = S0.put(compute, Compute1),
    %% Render the deliveries-overview table on the main page (PY:199-213).
    Deliveries = Results.get(deliveries, []),
    render_deliveries_overview(Role, Deliveries, S1, S2),
    %% Update the sidebar overview placeholder for this role (PY:213).
    PatientId = Results.get(patient_id, ''),
    PatientName = Results.get(patient_name, ''),
    total_mu_for_deliveries(Deliveries, TotalMu),
    render_overview_block(Role, PatientId, PatientName, TotalMu, S2, S).

%% Sum total MU across deliveries; mirrors PY:151-170 (display_deliveries body).
total_mu_for_deliveries([], 0).
total_mu_for_deliveries(Deliveries, TotalMu) :-
    Deliveries = [_|_],
    foldl(add_delivery_mu, Deliveries, 0, TotalMu).
add_delivery_mu(Delivery, Acc, Sum) :-
    %% In the source: total_mu = delivery.mu[-1] if num_control_points != 0 else 0
    %% Modeled here as an opaque accessor; the actual sum is computed at
    %% render time, not LTS time.
    DeliveryMu = Delivery.get(mu_total, 0),
    Sum is Acc + DeliveryMu.

%% Set the per-role dispatched tier so the DCG can route the next event.
set_input_method_dispatched_tier(Role, Method, S0, S) :-
    (   Role == reference
    ->  Tier = idle_reference_method_dispatched(Method)
    ;   Tier = idle_evaluation_method_dispatched(Method)
    ),
    S = S0.put(tier, Tier).
