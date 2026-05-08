%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Read-only operations: tier classifiers, sub-state classifiers, guard predicates,
%% and the small derivation cascade that folds widget state into the idle sub-state
%% atom. Pure functions of state{} -- no boundary calls, no mutation.

:- module(browse_ops, [
    % ==== Tier classifiers ====
    init_state/1,                   % init_state(+State)
    idle_state/1,                   % idle_state(+State)
    computing_state/1,              % computing_state(+State)
    displaying_state/1,             % displaying_state(+State)
    error_state/1,                  % error_state(+State)
    user_receptive_state/1,         % user_receptive_state(+State)
    internal_trace_state/1,         % internal_trace_state(+State)

    % ==== Sub-state classifiers ====
    idle_no_files/1,                % idle_no_files(+State)
    idle_files_uploaded/1,          % idle_files_uploaded(+State)
    computing_chunking/1,
    computing_per_chunk/1,
    computing_per_file/1,
    computing_zip_assembled/1,

    % ==== Guards (gating widget-event handlers) ====
    files_present/1,                % files_present(+State)
    files_absent/1,                 % files_absent(+State)
    button_clicked/1,               % button_clicked(+State)
    bad_data_set/1,                 % bad_data_set(+State)

    % ==== Derivation ====
    derive_idle_substate/2,         % derive_idle_substate(+State0, -State)
    derive_state/2                  % derive_state(+State0, -State)
]).

:- use_module(uploaded_file_list, [is_empty/1, file_count/2]).

% ============================================================
% Tier classifiers
% ============================================================

init_state(State) :- State.tier == init.

idle_state(State) :- (State.tier == idle_no_files ; State.tier == idle_files_uploaded), !.

computing_state(State) :-
    member(State.tier, [
        computing_chunking,
        computing_per_chunk,
        computing_per_file,
        computing_zip_assembled
    ]).
%% Note: tier is a parameterised compound for per_chunk/per_file (e.g.
%% `computing_per_chunk(3, 10)`), but the head functor is what classifies the tier.
%% The DCG threads the parameterised form for trace fidelity; the classifier
%% strips parameters via the helper below.
computing_state(State) :-
    nonvar(State.tier),
    compound(State.tier),
    functor(State.tier, F, _),
    member(F, [computing_per_chunk, computing_per_file, computing_zip_assembled]).

displaying_state(State) :- State.tier == displaying_results.

error_state(State) :- State.tier == error_bad_data.

%% PY: bisimulation distinction articulated in skill SKILL.md "Two-tier state model".
%% User-receptive states are where the script is paused awaiting widget input.
user_receptive_state(State) :-
    member(State.tier, [
        init,
        idle_no_files,
        idle_files_uploaded,
        displaying_results,
        error_bad_data
    ]).

internal_trace_state(State) :-
    \+ user_receptive_state(State).

% ============================================================
% Sub-state classifiers
% ============================================================

idle_no_files(State) :- State.tier == idle_no_files.
idle_files_uploaded(State) :- State.tier == idle_files_uploaded.

computing_chunking(State) :- State.tier == computing_chunking.

computing_per_chunk(State) :-
    nonvar(State.tier),
    State.tier =.. [computing_per_chunk | _].

computing_per_file(State) :-
    nonvar(State.tier),
    State.tier =.. [computing_per_file | _].

computing_zip_assembled(State) :-
    nonvar(State.tier),
    State.tier =.. [computing_zip_assembled | _].

% ============================================================
% Guards
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:163
%%     if file_buffer_list is not None and len(file_buffer_list) > 0:
%% Modeled here as a pure check on `widgets.dicom_uploader`. The `is not None`
%% half is collapsed because Streamlit's file_uploader returns [] when empty
%% in the widget-rendered state, never None (None only appears pre-first-render,
%% which the LTS handles via the `init` tier).
files_present(State) :-
    \+ is_empty(State.widgets.dicom_uploader).

files_absent(State) :-
    is_empty(State.widgets.dicom_uploader).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:239
%%     if st.button("Pseudonymise", key="PseudonymiseButton"):
button_clicked(State) :-
    State.widgets.pseudonymise_button == true.

bad_data_set(State) :-
    State.compute.bad_data == true.

% ============================================================
% Derivation
% ============================================================

%% Folds widget state into the idle sub-state atom. Called from any step//2
%% rule that may have changed `widgets.dicom_uploader` or transitioned into
%% the idle tier from elsewhere.
derive_idle_substate(S0, S) :-
    (   files_present(S0)
    ->  S = S0.put(tier, idle_files_uploaded)
    ;   S = S0.put(tier, idle_no_files)
    ).

%% derive_state/2 -- the cascade. Re-applies idle-substate derivation when the
%% current tier is in the idle family or transitioning back to idle. For
%% computing/displaying/error tiers, no derivation is required (those tiers
%% set their own tier explicitly in widget_ops/compute_ops).
derive_state(S0, S) :-
    (   member(S0.tier, [idle_no_files, idle_files_uploaded])
    ->  derive_idle_substate(S0, S)
    ;   S = S0
    ).
