%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py
%%
%% Top-level widget event handlers for the metersetmap LTS. One predicate
%% per widget call site in main.py + per-namespace selectbox dispatch.
%% Per-input-method widget handlers are STUBBED in input_method_stubs.pl.
%%
%% Each predicate updates `state.widgets` and may transition the tier.
%% The DCG is the dispatcher; these predicates do the actual mutation.

:- module(widget_ops, [
    % ==== Sidebar ====
    config_mode_selected/3,             % config_mode_selected(+Mode, +State0, -State)
    advanced_mode_toggled/3,            % advanced_mode_toggled(+Bool, +State0, -State)
    status_check_clicked/2,             % status_check_clicked(+State0, -State)
    compare_baseline_clicked/2,         % compare_baseline_clicked(+State0, -State)

    % ==== Main page top-level ====
    reference_method_selected/3,        % reference_method_selected(+Method, +State0, -State)
    evaluation_method_selected/3,       % evaluation_method_selected(+Method, +State0, -State)
    escan_site_selected/3,              % escan_site_selected(+Site, +State0, -State)
    png_output_directory_changed/3,     % png_output_directory_changed(+Path, +State0, -State)
    run_calculation_clicked/2           % run_calculation_clicked(+State0, -State)
]).

:- use_module(browse_ops, [derive_state/2, advanced_mode_active/1, can_run_calculation/1]).

% ============================================================
% Sidebar widget handlers
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:591-592
%%     config_mode = st.sidebar.radio("Config Mode", options=config_options)
%%     config = _config.get_config(config_mode)
%%
%% Selecting a config mode loads a different on-disk TOML; in the LTS this
%% invalidates downstream caches (since the config influences directory paths,
%% Mosaiq topology, gamma defaults). For the orchestration-first build we
%% don't model the cache invalidation explicitly -- a real metersetmap rerun
%% with a different config_mode would re-load everything.
config_mode_selected(Mode, S0, S) :-
    W1 = S0.widgets.put(config_mode, Mode),
    S1 = S0.put(widgets, W1),
    %% Transition init -> configuring_mode on first selection.
    (   S0.tier == init
    ->  S2 = S1.put(tier, idle_reference_selecting_method)
    ;   S2 = S1
    ),
    derive_state(S2, S).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:636
%%     advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")
%%
%% Toggles a flag that gates several widgets:
%%   - the Data Input Method selectbox (PY:181-187)
%%   - the per-input-method advanced widgets (Patient ID in iCOM, etc.)
%%   - the png_output_directory text_input (PY:737-749)
%%   - the Advanced Debugging panel (PY:787-788, advanced_debugging)
%%   - st.write(escan_directory) preview at :733
%%
%% In the LTS, toggling advanced_mode does NOT change the tier directly; it
%% changes which widget events are legal in subsequent reruns. The DCG's
%% guards check advanced_mode_active/1 to gate those events.
advanced_mode_toggled(Bool, S0, S) :-
    W1 = S0.widgets.put(advanced_mode, Bool),
    S = S0.put(widgets, W1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:101-138
%%     if st.sidebar.button("Check status of iCOM and backups"):
%%         try:
%%             linac_icom_live_stream_directories = _config.get_icom_live_stream_directories(config)
%%             linac_indexed_backups_directory = _config.get_indexed_backups_directory(config)
%%         except KeyError:
%%             st.sidebar.write(_exceptions.ConfigMissing(...))
%%             return
%%         ...
%%         for linac_id, icom_directory in linac_icom_live_stream_directories.items():
%%             icom_status(linac_id, icom_directory)
%%         ...
%%         for linac_id in linac_ids:
%%             trf_status(linac_id, linac_indexed_backups_directory)
%%
%% On click: scans configured iCOM + TRF backup directories, finds the most
%% recent file in each, prints "{linac_id}: `<timeago>`" to the sidebar.
%% The LTS treats this as a side-LTS -- it doesn't change reference/evaluation
%% state; just appends to sidebar.icom_status_lines and sidebar.trf_status_lines.
%%
%% On KeyError: the ConfigMissing exception is rendered via st.sidebar.write
%% and the handler returns early. We model that as a transient
%% error_config_missing tier that the next non-button event will leave.
status_check_clicked(S0, S) :-
    %% Two outcomes: success (populate status lines) or KeyError (transient error).
    %% In the orchestration-first build we collapse the two into a single
    %% transition with a guard distinguishing them; the actual scan is in
    %% compute_ops:run_status_check_pipeline (called via the DCG).
    W1 = S0.widgets.put(status_check_button, true),
    S = S0.put(widgets, W1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:373-434
%%     if st.sidebar.button("Compare Baseline to Output Directory"):
%%         ... advanced_debugging body ...
%%
%% Advanced-mode-only debug panel; iterates baseline PNG files and compares
%% against output PNGs via numpy.allclose. Not state-bearing for the main
%% wizard; treated as a side-LTS like status_check.
compare_baseline_clicked(S0, S) :-
    advanced_mode_active(S0),
    W1 = S0.widgets.put(compare_baseline_button, true),
    S = S0.put(widgets, W1).

% ============================================================
% Main page top-level widget handlers
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:678-684 (Reference)
%%     reference_results = get_input_data_ui(
%%         overview_updater_map,
%%         data_method_map,
%%         default_reference,
%%         "reference",
%%         advanced_mode,
%%     )
%%     -> get_input_data_ui:181-187
%%        if advanced_mode:
%%            data_method = st.selectbox("Data Input Method", data_method_options, ...)
%%
%% In non-advanced mode `data_method` is fixed at the config's default; only
%% advanced_mode lets the user choose. Both branches dispatch to
%% data_method_map[data_method]() which is one of the input_method_stubs entries.
reference_method_selected(Method, S0, S) :-
    advanced_mode_active(S0),
    Ref0 = S0.widgets.reference,
    Ref1 = Ref0.put(data_method, Method),
    W1 = S0.widgets.put(reference, Ref1),
    %% Transition into the per-method idle state.
    Tier = idle_reference_method_dispatched(Method),
    S = S0.put(_{widgets: W1, tier: Tier}).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:693-700 (Evaluation)
%% Same shape as reference_method_selected, with the namespace differing.
evaluation_method_selected(Method, S0, S) :-
    advanced_mode_active(S0),
    Eval0 = S0.widgets.evaluation,
    Eval1 = Eval0.put(data_method, Method),
    W1 = S0.widgets.put(evaluation, Eval1),
    Tier = idle_evaluation_method_dispatched(Method),
    S = S0.put(_{widgets: W1, tier: Tier}).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:722-728
%%     _, escan_directory = st_misc.get_site_and_directory(
%%         config, "eScan Site", "escan", default=default_site, key="escan_export_site_picker"
%%     )
escan_site_selected(Site, S0, S) :-
    W1 = S0.widgets.put(escan_site, Site),
    S1 = S0.put(widgets, W1),
    derive_state(S1, S).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:746-748 (advanced-mode only)
%%     png_output_directory = pathlib.Path(
%%         st.text_input("png output directory", default_png_output_directory)
%%     )
png_output_directory_changed(Path, S0, S) :-
    advanced_mode_active(S0),
    W1 = S0.widgets.put(png_output_directory, Path),
    S = S0.put(widgets, W1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:764-785
%%     if st.button("Run Calculation"):
%%         st.write("### MetersetMap usage warning")
%%         st.warning(pymedphys.metersetmap.WARNING_MESSAGE)
%%         st.write("### Calculation status")
%%         run_calculation(reference_results, evaluation_results, gamma_options,
%%                         escan_directory, png_output_directory)
%%
%% Three sub-cases by guard:
%%   (a) can_run_calculation -> dispatch to compute pipeline. Tier transitions
%%       through the modal_warning_metersetmap_usage state on entry to the
%%       `st.warning(...)` call (modal-tier first-class state per SKILL.md),
%%       then progresses through the computing_* internal-trace states, then
%%       to displaying_results.
%%   (b) reference_results missing or evaluation_results missing -> the click
%%       still fires, but get_input_data_ui returns empty for the missing one
%%       and run_calculation crashes on `reference_results["deliveries"]`
%%       KeyError. In practice users learn not to click prematurely; the
%%       orchestration-first build models this as a no-op (button does nothing
%%       meaningful) with the tier preserved. A more rigorous model would
%%       add an error_premature_calculation tier.
run_calculation_clicked(S0, S) :-
    can_run_calculation(S0),
    !,
    W1 = S0.widgets.put(run_calculation_button, true),
    S1 = S0.put(widgets, W1),
    %% Transition to the modal warning. compute_ops:run_calculation_pipeline/2
    %% (called from the DCG) walks from modal back through the computing tiers
    %% to displaying_results.
    S = S1.put(tier, modal_warning_metersetmap_usage).
run_calculation_clicked(S0, S) :-
    %% Premature click; no state change.
    \+ can_run_calculation(S0),
    W1 = S0.widgets.put(run_calculation_button, false),
    S = S0.put(widgets, W1).
