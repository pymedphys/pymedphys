%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Widget-event handlers -- the mutating predicates triggered by user
%% interactions with the file_uploader and the Pseudonymise button. Each
%% predicate updates `state.widgets`, may set the tier into `computing_*`,
%% and dispatches to compute_ops if applicable.
%%
%% This app has exactly two interactive widgets:
%%   - st.file_uploader (PY:233-237) -- emits upload(files) / clear_upload events
%%   - st.button       (PY:239)      -- emits click(pseudonymise_button) events
%%
%% Both fire once per rerun. Streamlit's runtime gathers the next user event,
%% reruns the whole script, and the new widget-call return values reflect
%% that user event.

:- module(widget_ops, [
    upload_dicom_files/3,           % upload_dicom_files(+NewFileList, +State0, -State)
    clear_dicom_files/2,            % clear_dicom_files(+State0, -State)
    pseudonymise_button_click/2     % pseudonymise_button_click(+State0, -State)
]).

:- use_module(browse_ops, [files_present/1, derive_idle_substate/2]).
:- use_module(compute_ops, [run_pseudonymise_pipeline/2]).
:- use_module(uploaded_file_list, [file_count/2]).

% ============================================================
% File uploader: non-empty -> idle_files_uploaded
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:233-237
%%     uploaded_file_buffer_list = st.file_uploader(...)
%% This handler fires when the file_uploader returns a non-empty list -- either
%% on the first non-empty rerun OR when the user adds files to an existing list.
upload_dicom_files(Files, S0, S) :-
    Files = [_|_],                  %% guard: non-empty
    file_count(Files, N),
    W1 = S0.widgets.put(dicom_uploader, Files),
    C1 = S0.compute.put(file_count, N),
    S1 = S0.put(_{widgets: W1, compute: C1}),
    S2 = S1.put(tier, idle_files_uploaded).
    %% derive_idle_substate is redundant here -- we know we are in idle_files_uploaded
    %% because Files is non-empty. The DCG calls derive_state/2 anyway as a defensive
    %% no-op for tier-discipline.
upload_dicom_files(Files, S0, S) :-
    %% Trailing rebind so derive_state/2 sees the updated dict.
    Files = [_|_],
    upload_dicom_files_inner(Files, S0, S).

upload_dicom_files_inner(Files, S0, S) :-
    file_count(Files, N),
    W1 = S0.widgets.put(dicom_uploader, Files),
    C1 = S0.compute.put(file_count, N),
    S = S0.put(_{widgets: W1, compute: C1, tier: idle_files_uploaded}).

% ============================================================
% File uploader: empty -> idle_no_files
% ============================================================

%% PY: implicit in the file_uploader contract -- when the user clicks the X to
%% remove all files, the widget returns [] on the next rerun. The pseudonymise
%% script does NOT explicitly handle this transition; the next button click
%% will simply no-op via the `len(file_buffer_list) > 0` guard at PY:163.
%%
%% Modeled here for operational fidelity even though the source has no
%% explicit handler -- the LTS captures the observable transition.
clear_dicom_files(S0, S) :-
    W1 = S0.widgets.put(dicom_uploader, []),
    C1 = S0.compute.put(file_count, 0),
    S = S0.put(_{widgets: W1, compute: C1, tier: idle_no_files}).

% ============================================================
% Pseudonymise button click: dispatch to compute pipeline
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:239-241
%%     if st.button("Pseudonymise", key="PseudonymiseButton"):
%%         pseudonymise_buffer_list(uploaded_file_buffer_list)
%%         uploaded_file_buffer_list.clear()
%%
%% Three branches by guard:
%%   1. files present  -> dispatch to compute pipeline (compute_ops:run_pseudonymise_pipeline/2)
%%   2. files absent   -> no-op (PY:163 length-guard fails inside pseudonymise_buffer_list)
%%   3. button never True on this rerun -> handler does not fire (covered by DCG step//2 dispatch)
%%
%% ⚠ Python source quirk preserved verbatim:
%%     `uploaded_file_buffer_list.clear()` at PY:241 mutates the LOCAL Python list,
%%     not Streamlit's widget state. On the next rerun the file_uploader still has
%%     the user's uploads; Streamlit's runtime owns widget-state, not the script's
%%     local variables. So post-click, the LTS transitions to displaying_results
%%     (or error_bad_data), and the NEXT widget event (likely an upload of
%%     replacement files or a clear via the X-button) will leave the LTS in
%%     idle_files_uploaded, NOT idle_no_files.
pseudonymise_button_click(S0, S) :-
    files_present(S0),
    !,
    %% Mark the button as clicked in the widget-state slot for trace fidelity.
    W1 = S0.widgets.put(pseudonymise_button, true),
    S1 = S0.put(widgets, W1),
    %% Dispatch to compute pipeline. compute_ops:run_pseudonymise_pipeline/2 walks
    %% the chunk list, emitting the side-effect-stream labels and updating the
    %% compute-tier sub-states as it goes; it terminates in either
    %% displaying_results (success) or error_bad_data (exception caught).
    run_pseudonymise_pipeline(S1, S2),
    %% After pipeline returns, reset the button widget-state back to false.
    %% Streamlit's button widget is edge-triggered: it returns True only on the
    %% rerun immediately following the click, then False on subsequent reruns.
    W2 = S2.widgets.put(pseudonymise_button, false),
    S = S2.put(widgets, W2).
pseudonymise_button_click(S0, S) :-
    %% files_absent branch: PY:163 guard fails, the helper returns immediately
    %% without doing any work or rendering anything. Tier stays idle_no_files.
    \+ files_present(S0),
    %% Still toggle the edge-triggered button back to false.
    W1 = S0.widgets.put(pseudonymise_button, false),
    S = S0.put(widgets, W1).
