%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py
%%
%% The DCG itself for the metersetmap orchestrator. One step//2 rule per
%% (event terminal x distinguishing-guard) pair, threaded over a state{}
%% SWI-Prolog dict. All actual mutation is delegated to widget_ops /
%% compute_ops / render_ops / save_pipeline / input_method_stubs / browse_ops;
%% step//2 rules pattern-match the event, check guards, dispatch, and update
%% the tier.
%%
%% Two-tier state model (per python-streamlit-state-model SKILL.md):
%%   USER-RECEPTIVE STATES (between reruns; the script is paused awaiting input):
%%     init,
%%     configuring_mode,
%%     idle_reference_selecting_method,
%%     idle_reference_method_dispatched(Method),     [stubbed sub-LTS]
%%     idle_evaluation_selecting_method,
%%     idle_evaluation_method_dispatched(Method),    [stubbed sub-LTS]
%%     configuring_output_escan,
%%     configuring_output_png,                       [advanced-only]
%%     ready_to_calculate,
%%     modal_warning_metersetmap_usage,
%%     displaying_results,
%%     error_pdf_conversion,
%%     error_config_missing,
%%     error_file_not_found_baseline,
%%     viewing_icom_status, viewing_trf_status,      [sidebar status panel]
%%     comparing_baseline_to_output,                 [advanced-debugging]
%%     displaying_baseline_diff
%%
%%   INTERNAL-TRACE STATES (within a single rerun's transitions):
%%     computing_reference_metersetmap,
%%     computing_evaluation_metersetmap,
%%     computing_per_delivery(Role, I),
%%     computing_gamma,
%%     computing_plot,
%%     computing_png_save,
%%     computing_pdf_convert
%%
%% Event alphabet (orchestration-first scope; per-input-method events are
%% collapsed to `input_method_returned/3` per the stub-module contract):
%%
%%   - init
%%   - select(config_mode, ConfigMode)
%%   - toggle(advanced_mode, Bool)
%%   - click(status_check_button)
%%   - click(compare_baseline_button)         [advanced-only guard]
%%   - select(reference_method, Method)        [advanced-only guard]
%%   - select(evaluation_method, Method)       [advanced-only guard]
%%   - input_method_returned(reference, Method, Results)   [stubbed sub-LTS exit]
%%   - input_method_returned(evaluation, Method, Results)  [stubbed sub-LTS exit]
%%   - select(escan_site, Site)
%%   - text_change(png_output_directory, Path) [advanced-only guard]
%%   - click(run_calculation_button)           [can_run_calculation guard]
%%
%% Side-effect-stream labels are emitted within the bodies of the ops modules;
%% they appear in the DCG's input list interleaved with the user events. See
%% the markdown narrative Section 3 for the full enumeration.

:- module(ui_state_dcg, [
    initial_state/1,                % initial_state(-State)
    step//2,                        % step(+State0, -State, +EventStream, -RestStream)
    valid_next/2,                   % valid_next(+State, -EventTerminal)
    valid_sequence/1                % valid_sequence(+EventList)
]).

:- use_module(session_record, [initial_state/1]).
:- use_module(browse_ops, [
    init_state/1,
    user_receptive_state/1,
    advanced_mode_active/1,
    can_run_calculation/1,
    derive_state/2
]).
:- use_module(widget_ops, [
    config_mode_selected/3,
    advanced_mode_toggled/3,
    status_check_clicked/2,
    compare_baseline_clicked/2,
    reference_method_selected/3,
    evaluation_method_selected/3,
    escan_site_selected/3,
    png_output_directory_changed/3,
    run_calculation_clicked/2
]).
:- use_module(input_method_stubs, [dispatch_input_method/5]).
:- use_module(compute_ops, [
    run_calculation_pipeline/2,
    run_status_check_pipeline/2,
    run_advanced_debugging_pipeline/2
]).

% ============================================================
% step//2 rules
% ============================================================

%% --------------------------------------------------------------
%% init -- the first script execution
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:571 -- def main()
step(S0, S) -->
    [init],
    { init_state(S0) },
    { S = S0.put(tier, configuring_mode) }.

%% --------------------------------------------------------------
%% select(config_mode, Mode) -- sidebar Config Mode radio
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:591
%%     config_mode = st.sidebar.radio("Config Mode", options=config_options)
%% Streamlit auto-selects the first option on first render. Subsequent reruns
%% can change it via user click on a different option.
step(S0, S) -->
    [select(config_mode, Mode)],
    { user_receptive_state(S0) },
    { config_mode_selected(Mode, S0, S) }.

%% --------------------------------------------------------------
%% toggle(advanced_mode, Bool) -- sidebar Advanced Mode checkbox
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:636
%%     advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")
step(S0, S) -->
    [toggle(advanced_mode, Bool)],
    { user_receptive_state(S0) },
    { advanced_mode_toggled(Bool, S0, S1) },
    { derive_state(S1, S) }.

%% --------------------------------------------------------------
%% click(status_check_button) -- sidebar status indicators button
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:102
%%     if st.sidebar.button("Check status of iCOM and backups"):
%%
%% Two outcomes:
%%   - success: scan succeeds, sidebar status lines populated.
%%     Tier transitions through viewing_icom_status -> viewing_trf_status,
%%     ending in viewing_trf_status (the user's prior tier is NOT preserved).
%%   - error_config_missing: KeyError on config lookup.
step(S0, S) -->
    [click(status_check_button)],
    { user_receptive_state(S0) },
    { status_check_clicked(S0, S1) },
    { run_status_check_pipeline(S1, S2) },
    { derive_state(S2, S) }.

%% --------------------------------------------------------------
%% click(compare_baseline_button) -- advanced-debugging button
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:375
%%     if st.sidebar.button("Compare Baseline to Output Directory"):
%% Advanced-mode-only.
step(S0, S) -->
    [click(compare_baseline_button)],
    { advanced_mode_active(S0) },
    { user_receptive_state(S0) },
    { compare_baseline_clicked(S0, S1) },
    { run_advanced_debugging_pipeline(S1, S) }.

%% --------------------------------------------------------------
%% select(reference_method, Method) -- advanced-mode Data Input Method selectbox
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:678-684 (Reference column),
%%     dispatching to get_input_data_ui:181-187 selectbox.
%% Advanced-mode-only; in non-advanced mode the method is fixed at the
%% config default and there's no event to fire.
step(S0, S) -->
    [select(reference_method, Method)],
    { advanced_mode_active(S0) },
    { user_receptive_state(S0) },
    { reference_method_selected(Method, S0, S) }.

%% --------------------------------------------------------------
%% select(evaluation_method, Method) -- evaluation-column selectbox
%% --------------------------------------------------------------
step(S0, S) -->
    [select(evaluation_method, Method)],
    { advanced_mode_active(S0) },
    { user_receptive_state(S0) },
    { evaluation_method_selected(Method, S0, S) }.

%% --------------------------------------------------------------
%% input_method_returned(Role, Method, Results) -- stubbed sub-LTS exit
%% --------------------------------------------------------------
%% Stand-in for the per-method sub-LTS terminal transitions. In the
%% orchestration-first build, all 5 input methods (dicom/icom/trf/mosaiq/monaco)
%% reduce to this single event terminal whose payload is the per-method
%% results dict. Phase-2 expansion will replace this with method-specific
%% events (upload(K, files), select(K, plan), text_change(K, val), etc.).
step(S0, S) -->
    [input_method_returned(Role, Method, Results)],
    { user_receptive_state(S0) },
    { member(Role, [reference, evaluation]) },
    { member(Method, [dicom, icom, trf, mosaiq, monaco]) },
    { dispatch_input_method(Role, Method, Results, S0, S) }.

%% --------------------------------------------------------------
%% select(escan_site, Site) -- eSCAN directory site picker
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:722-728
%%     _, escan_directory = st_misc.get_site_and_directory(...)
step(S0, S) -->
    [select(escan_site, Site)],
    { user_receptive_state(S0) },
    { escan_site_selected(Site, S0, S) }.

%% --------------------------------------------------------------
%% text_change(png_output_directory, Path) -- advanced-mode text_input
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:746-748
%%     png_output_directory = pathlib.Path(st.text_input("png output directory", default))
step(S0, S) -->
    [text_change(png_output_directory, Path)],
    { advanced_mode_active(S0) },
    { user_receptive_state(S0) },
    { png_output_directory_changed(Path, S0, S) }.

%% --------------------------------------------------------------
%% click(run_calculation_button) -- the BIG one
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:764-785
%%     if st.button("Run Calculation"):
%%         st.write("### MetersetMap usage warning")
%%         st.warning(pymedphys.metersetmap.WARNING_MESSAGE)
%%         st.write("### Calculation status")
%%         run_calculation(reference_results, evaluation_results, gamma_options,
%%                         escan_directory, png_output_directory)
%%
%% Two sub-cases by guard:
%%   (a) can_run_calculation -> dispatch to run_calculation_pipeline. Tier
%%       transitions through modal_warning_metersetmap_usage,
%%       computing_reference_metersetmap, computing_evaluation_metersetmap,
%%       computing_per_delivery(Role, I) inside each, computing_gamma,
%%       computing_plot, computing_png_save, computing_pdf_convert,
%%       ending in displaying_results OR error_pdf_conversion.
%%   (b) NOT can_run_calculation -> the click still fires but the pipeline
%%       short-circuits (run_calculation_clicked second clause). No tier
%%       change. The button remains visible in subsequent reruns.

step(S0, S) -->
    [click(run_calculation_button)],
    { user_receptive_state(S0) },
    { can_run_calculation(S0) },
    { run_calculation_clicked(S0, S1) },
    { run_calculation_pipeline(S1, S) }.

step(S0, S) -->
    [click(run_calculation_button)],
    { user_receptive_state(S0) },
    { \+ can_run_calculation(S0) },
    { run_calculation_clicked(S0, S) }.

% ============================================================
% Helpers
% ============================================================

%% valid_next(+State, -Event) -- enumerate legal events from a user-receptive
%% state. Used by tests / interactive exploration. Internal-trace states have
%% no legal user events (script is mid-rerun).
valid_next(S, init) :- init_state(S).
valid_next(S, select(config_mode, _)) :- user_receptive_state(S).
valid_next(S, toggle(advanced_mode, _)) :- user_receptive_state(S).
valid_next(S, click(status_check_button)) :- user_receptive_state(S).
valid_next(S, click(compare_baseline_button)) :-
    user_receptive_state(S), advanced_mode_active(S).
valid_next(S, select(reference_method, _)) :-
    user_receptive_state(S), advanced_mode_active(S).
valid_next(S, select(evaluation_method, _)) :-
    user_receptive_state(S), advanced_mode_active(S).
valid_next(S, input_method_returned(reference, _, _)) :-
    user_receptive_state(S).
valid_next(S, input_method_returned(evaluation, _, _)) :-
    user_receptive_state(S).
valid_next(S, select(escan_site, _)) :- user_receptive_state(S).
valid_next(S, text_change(png_output_directory, _)) :-
    user_receptive_state(S), advanced_mode_active(S).
valid_next(S, click(run_calculation_button)) :- user_receptive_state(S).

%% valid_sequence(+Events) -- replay a sequence from initial_state.
valid_sequence(Events) :-
    initial_state(S0),
    phrase(steps(S0, _Final), Events).

steps(S, S) --> [].
steps(S0, S) -->
    step(S0, S1),
    steps(S1, S).
