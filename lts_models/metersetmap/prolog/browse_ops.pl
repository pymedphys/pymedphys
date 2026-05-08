%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py + sibling modules
%%
%% Read-only operations for the metersetmap LTS: tier classifiers, sub-state
%% classifiers, guard predicates, and derivation cascades. Pure functions of
%% state{} -- no boundary calls, no mutation.

:- module(browse_ops, [
    % ==== Tier classifiers ====
    init_state/1,
    configuring_state/1,
    selecting_reference_state/1,
    selecting_evaluation_state/1,
    configuring_output_state/1,
    ready_to_calculate_state/1,
    computing_state/1,
    modal_state/1,
    displaying_state/1,
    error_state/1,
    sidebar_status_view_state/1,
    advanced_debugging_state/1,
    user_receptive_state/1,
    internal_trace_state/1,

    % ==== Sub-state and condition classifiers ====
    config_chosen/1,
    advanced_mode_active/1,
    reference_results_present/1,
    evaluation_results_present/1,
    both_results_present/1,
    escan_directory_chosen/1,
    output_config_complete/1,
    can_run_calculation/1,

    % ==== Cache classifiers ====
    cache_slot_empty/2,
    cache_slot_stored/3,

    % ==== Derivation ====
    derive_state/2,                 % derive_state(+State0, -State)
    derive_ready_to_calculate/2     % derive_ready_to_calculate(+State0, -State)
]).

:- use_module(cache_registry, [all_cache_slots/1]).

% ============================================================
% Tier classifiers
% ============================================================

init_state(State) :- State.tier == init.

configuring_state(State) :- State.tier == configuring_mode.

selecting_reference_state(State) :-
    nonvar(State.tier),
    (   State.tier == idle_reference_selecting_method
    ;   functor_subtree(State.tier, idle_reference_dicom)
    ;   functor_subtree(State.tier, idle_reference_icom)
    ;   functor_subtree(State.tier, idle_reference_trf)
    ;   functor_subtree(State.tier, idle_reference_mosaiq)
    ;   functor_subtree(State.tier, idle_reference_monaco)
    ).

selecting_evaluation_state(State) :-
    nonvar(State.tier),
    (   State.tier == idle_evaluation_selecting_method
    ;   functor_subtree(State.tier, idle_evaluation_dicom)
    ;   functor_subtree(State.tier, idle_evaluation_icom)
    ;   functor_subtree(State.tier, idle_evaluation_trf)
    ;   functor_subtree(State.tier, idle_evaluation_mosaiq)
    ;   functor_subtree(State.tier, idle_evaluation_monaco)
    ).

%% Helper: tree-pattern test for compound tiers (e.g. idle_reference_dicom_file_upload).
%% In the orchestration-first build, the per-input-method sub-states are
%% collapsed to a single `idle_<role>_<method>_returned` atom (see
%% input_method_stubs.pl); the inner sub-states are DEFERRED.
functor_subtree(Tier, FunctorPattern) :-
    nonvar(Tier),
    (   Tier == FunctorPattern
    ;   compound(Tier),
        functor(Tier, F, _),
        F == FunctorPattern
    ).

configuring_output_state(State) :-
    member(State.tier, [configuring_output_escan, configuring_output_png]).

ready_to_calculate_state(State) :- State.tier == ready_to_calculate.

computing_state(State) :-
    nonvar(State.tier),
    (   member(State.tier, [
            computing_reference_metersetmap,
            computing_evaluation_metersetmap,
            computing_gamma,
            computing_plot,
            computing_png_save,
            computing_pdf_convert
        ])
    ;   compound(State.tier),
        functor(State.tier, F, _),
        member(F, [computing_per_delivery])
    ).

modal_state(State) :- State.tier == modal_warning_metersetmap_usage.

displaying_state(State) :- State.tier == displaying_results.

error_state(State) :-
    member(State.tier, [
        error_wrong_dicom_type,
        error_no_records,
        error_input_required,
        error_unknown_patient,
        error_no_control_points,
        error_pdf_conversion,
        error_config_missing,
        error_file_not_found_baseline,
        error_dicom_extraction_value
    ]).

sidebar_status_view_state(State) :-
    member(State.tier, [viewing_icom_status, viewing_trf_status]).

advanced_debugging_state(State) :-
    member(State.tier, [comparing_baseline_to_output, displaying_baseline_diff]).

user_receptive_state(State) :-
    (   init_state(State)
    ;   configuring_state(State)
    ;   selecting_reference_state(State)
    ;   selecting_evaluation_state(State)
    ;   configuring_output_state(State)
    ;   ready_to_calculate_state(State)
    ;   modal_state(State)
    ;   displaying_state(State)
    ;   error_state(State)
    ;   sidebar_status_view_state(State)
    ;   advanced_debugging_state(State)
    ).

internal_trace_state(State) :-
    \+ user_receptive_state(State).

% ============================================================
% Sub-state and condition classifiers
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:591-592
%%     config_mode = st.sidebar.radio("Config Mode", options=config_options)
%%     config = _config.get_config(config_mode)
%% Streamlit auto-selects the first option on first render (st.sidebar.radio
%% always returns one of `options`), so config_mode is rarely _unset in
%% practice. For LTS rigour we treat _unset as "not yet rendered" (init only).
config_chosen(State) :-
    State.widgets.config_mode \== _unset.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:636
advanced_mode_active(State) :-
    State.widgets.advanced_mode == true.

reference_results_present(State) :-
    State.compute.reference_results \== none,
    nonvar(State.compute.reference_results),
    is_dict(State.compute.reference_results),
    get_dict(deliveries, State.compute.reference_results, Deliveries),
    Deliveries = [_|_].

evaluation_results_present(State) :-
    State.compute.evaluation_results \== none,
    nonvar(State.compute.evaluation_results),
    is_dict(State.compute.evaluation_results),
    get_dict(deliveries, State.compute.evaluation_results, Deliveries),
    Deliveries = [_|_].

both_results_present(State) :-
    reference_results_present(State),
    evaluation_results_present(State).

escan_directory_chosen(State) :-
    State.widgets.escan_site \== _unset.

output_config_complete(State) :-
    escan_directory_chosen(State).
    %% png_output_directory has a non-advanced default at PY:735, :751-752, so
    %% it's never genuinely "missing" in non-advanced mode. In advanced mode
    %% the user can override but the text_input default is loaded.

can_run_calculation(State) :-
    both_results_present(State),
    output_config_complete(State).

% ============================================================
% Cache classifiers
% ============================================================

cache_slot_empty(State, Slot) :-
    get_dict(Slot, State.caches, _empty).

cache_slot_stored(State, Slot, Value) :-
    get_dict(Slot, State.caches, stored(_Key, Value)).

% ============================================================
% Derivation
% ============================================================

%% derive_ready_to_calculate/2 -- after any update to compute.reference_results,
%% compute.evaluation_results, or widgets.escan_site, re-evaluate whether the
%% Run Calculation button transition is armed. If yes AND the current tier is
%% not in computing/displaying/error, transition to ready_to_calculate.
derive_ready_to_calculate(S0, S) :-
    (   can_run_calculation(S0),
        \+ computing_state(S0),
        \+ displaying_state(S0),
        \+ error_state(S0),
        \+ modal_state(S0)
    ->  S = S0.put(tier, ready_to_calculate)
    ;   S = S0
    ).

%% derive_state/2 -- the cascade. Re-applies ready_to_calculate derivation
%% after every mutating step. For computing/error/modal/displaying tiers,
%% no derivation is required (those tiers set their own tier explicitly).
derive_state(S0, S) :-
    derive_ready_to_calculate(S0, S).
