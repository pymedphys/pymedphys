%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% The DCG itself. One step//2 rule per (event terminal x distinguishing-guard)
%% pair, threaded over a state{} SWI-Prolog dict. All actual mutation is
%% delegated to widget_ops / compute_ops / render_ops / browse_ops / boundary;
%% step//2 rules pattern-match the event, check guards, dispatch, and update
%% the tier.
%%
%% Two-tier state model (per SKILL.md):
%%   USER-RECEPTIVE STATES (between reruns; the script is paused awaiting input):
%%     init, idle_no_files, idle_files_uploaded, displaying_results, error_bad_data
%%   INTERNAL-TRACE STATES (within a single rerun's compute transition):
%%     computing_chunking, computing_per_chunk(I, N), computing_per_file(I, J),
%%     computing_zip_assembled(I)
%%
%% Each step//2 rule transitions between USER-RECEPTIVE states; internal-trace
%% states are visited within the rule body (via compute_ops:run_pseudonymise_pipeline/2)
%% and are NOT user-event-receptive. Only the user-receptive states appear as
%% top-level nodes in stm_primary.svg.
%%
%% Event alphabet (4 user events):
%%   - init                     -- first script execution
%%   - upload(K, Files)         -- file_uploader transitioned [] -> non-empty
%%   - clear_upload(K)          -- file_uploader transitioned non-empty -> []
%%   - click(pseudonymise_button) -- st.button returned True
%%
%% Side-effect-stream labels (interleaved within the click(...) transition --
%% see compute_ops.pl and render_ops.pl for the full enumeration):
%%   gen_chunks, render_chunk_indices, chunk_start, dcmread, anonymise_dataset,
%%   build_pseudonymised_filename, dcmwrite, zipfile_writestr, chunk_complete,
%%   render_download_link, render_error_text, print_exception
%%
%% Layout glue (st.title, st.columns, st.tabs, st.expander, st.divider, etc.)
%% omitted -- not state-bearing. pseudonymise.py has no layout calls anyway,
%% so the omission list is empty for this app.

:- module(ui_state_dcg, [
    initial_state/1,                % initial_state(-State)
    step//2,                        % step(+State0, -State, +EventStream, -RestStream)
    valid_next/2,                   % valid_next(+State, -EventTerminal)
    valid_sequence/1                % valid_sequence(+EventList)
]).

:- use_module(session_record, [initial_state/1]).
:- use_module(browse_ops, [
    init_state/1,
    idle_state/1,
    idle_no_files/1,
    idle_files_uploaded/1,
    displaying_state/1,
    error_state/1,
    user_receptive_state/1,
    files_present/1,
    files_absent/1,
    derive_state/2
]).
:- use_module(widget_ops, [
    upload_dicom_files/3,
    clear_dicom_files/2,
    pseudonymise_button_click/2
]).

% ============================================================
% step//2 rules
% ============================================================
%
% Naming: step(+S0, -S) where the event terminal is consumed from the DCG
% input list. Guard predicates appear in {}-curlies. The body delegates to
% widget_ops/compute_ops; never inlines mutation.

%% --------------------------------------------------------------
%% init -- the first script execution
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:232 -- def main()
%% Streamlit invokes main() on the first page load with empty widget state.
%% No user event has fired yet; the LTS transitions from `init` to its
%% post-render resting tier, which depends on whether the file_uploader had
%% any persisted state. For a fresh tab, the uploader is empty -> idle_no_files.
%% A persisted-session restoration could land in idle_files_uploaded; we model
%% the common path here.
step(S0, S) -->
    [init],
    { init_state(S0) },
    { S = S0.put(tier, idle_no_files) }.

%% --------------------------------------------------------------
%% upload(K, Files) -- file_uploader transitions to a non-empty list
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:233-237
%%     uploaded_file_buffer_list = st.file_uploader(
%%         "Files to pseudonymise, refresh page after downloading zip(s)",
%%         ["dcm"],
%%         accept_multiple_files=True,
%%     )
%% K = auto_file_uploader_0 (Streamlit auto-keys when no key= is supplied).
%% Three source tiers can receive this event: init, idle_no_files, idle_files_uploaded
%% (the user can replace the upload set without explicitly clearing first).
step(S0, S) -->
    [upload(auto_file_uploader_0, Files)],
    { Files = [_|_] },                        %% guard: non-empty list
    { member(S0.tier, [init, idle_no_files, idle_files_uploaded,
                       displaying_results, error_bad_data]) },
    { upload_dicom_files(Files, S0, S1) },
    { derive_state(S1, S) }.

%% --------------------------------------------------------------
%% clear_upload(K) -- file_uploader transitions non-empty -> []
%% --------------------------------------------------------------
%% PY: implicit in the file_uploader contract (no explicit handler in the source).
%% The user clicks the X next to the uploaded file list; on the next rerun
%% the widget returns []. The pseudonymise script does NOT branch on this
%% transition -- the next click(button) will simply no-op via the
%% PY:163 `len > 0` guard. Modeled here for operational fidelity.
step(S0, S) -->
    [clear_upload(auto_file_uploader_0)],
    { member(S0.tier, [idle_files_uploaded, displaying_results, error_bad_data]) },
    { clear_dicom_files(S0, S1) },
    { derive_state(S1, S) }.

%% --------------------------------------------------------------
%% click(pseudonymise_button) -- the Pseudonymise button was pressed
%% --------------------------------------------------------------
%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:239-241
%%     if st.button("Pseudonymise", key="PseudonymiseButton"):
%%         pseudonymise_buffer_list(uploaded_file_buffer_list)
%%         uploaded_file_buffer_list.clear()
%%
%% Three sub-cases by guard:
%%   (a) files_present -> dispatch to compute pipeline; tier ends in
%%       displaying_results (success) or error_bad_data (any chunk hit
%%       an exception in the inner try/except).
%%   (b) files_absent -> PY:163 guard fails inside pseudonymise_buffer_list,
%%       no work is done, no rendering happens. Tier stays idle_no_files.
%%   (c) error_bad_data tier -> the user can still click again with current
%%       (or replaced) files. We model a click from error_bad_data as the
%%       user retrying; behaviour matches case (a) or (b) by guard.

step(S0, S) -->
    [click(pseudonymise_button)],
    { member(S0.tier, [idle_files_uploaded, displaying_results, error_bad_data]) },
    { files_present(S0) },
    { pseudonymise_button_click(S0, S) }.

step(S0, S) -->
    [click(pseudonymise_button)],
    { S0.tier == idle_no_files },
    { files_absent(S0) },
    { pseudonymise_button_click(S0, S) }.   %% no-op branch; tier preserved

% ============================================================
% Helpers
% ============================================================

%% valid_next(+State, -Event) -- enumerate legal events from a user-receptive
%% state. Useful for tests and interactive exploration. Internal-trace states
%% have no legal user events (the script is mid-rerun, not paused).
valid_next(S, init) :- init_state(S).
valid_next(S, upload(auto_file_uploader_0, _)) :- user_receptive_state(S).
valid_next(S, clear_upload(auto_file_uploader_0)) :-
    member(S.tier, [idle_files_uploaded, displaying_results, error_bad_data]).
valid_next(S, click(pseudonymise_button)) :-
    member(S.tier, [idle_no_files, idle_files_uploaded,
                    displaying_results, error_bad_data]).

%% valid_sequence(+Events) -- replay a sequence from initial_state.
%% Succeeds iff every prefix corresponds to a legal step//2 trace.
valid_sequence(Events) :-
    initial_state(S0),
    phrase(steps(S0, _Final), Events).

steps(S, S) --> [].
steps(S0, S) -->
    step(S0, S1),
    steps(S1, S).
