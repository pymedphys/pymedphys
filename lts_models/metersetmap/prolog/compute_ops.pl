%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py
%%
%% Compute-pipeline ops -- the work that runs between the Run Calculation
%% click and the final result render. Mirrors:
%%
%%   run_calculation                  (PY:437-516)  -- top-level orchestration
%%   calculate_batch_metersetmap      (PY:351-357)  -- ref/eval metersetmap fold
%%   calculate_metersetmap            (PY:342-348, cached) -- per-delivery
%%   calculate_gamma                  (PY:360-370, cached) -- gamma kernel
%%   plot_and_save_results            (PY:236-339) -- 4 imageio.imwrite + figure
%%
%% Plus the secondary pipelines:
%%   show_status_indicators           (PY:101-138) -- sidebar status panel
%%   advanced_debugging               (PY:373-434) -- baseline diff panel
%%
%% Each predicate updates state.compute and emits side-effect-stream labels
%% via the boundary modules.

:- module(compute_ops, [
    run_calculation_pipeline/2,         % run_calculation_pipeline(+State0, -State)
    calculate_batch_metersetmap_op/4,   % calculate_batch_metersetmap_op(+Role, +Deliveries, +State0, -State)
    calculate_gamma_op/2,               % calculate_gamma_op(+State0, -State)
    plot_and_save_results_op/2,         % plot_and_save_results_op(+State0, -State)

    run_status_check_pipeline/2,        % run_status_check_pipeline(+State0, -State)
    run_advanced_debugging_pipeline/2   % run_advanced_debugging_pipeline(+State0, -State)
]).

:- use_module(streamlit_boundary, [
    st_warning/1,
    st_write/1,
    st_columns/2,
    plt_subplots/4,
    path_glob/3,
    path_resolve/2,
    path_mkdir/3,
    path_getmtime/2,
    path_is_file/1,
    datetime_now/1,
    datetime_fromtimestamp/2,
    timeago_format/3,
    imageio_imread/2
]).
:- use_module(algorithm_kernels, [
    delivery_metersetmap/5,
    pymedphys_gamma/6,
    metersetmap_display/4,
    normalize_to_uint8/4
]).
:- use_module(render_ops, [
    render_calculation_status/3,
    render_calculation_warning_modal/2,
    render_results_section/2,
    render_save_status/3,
    render_status_line/3
]).
:- use_module(save_pipeline, [
    save_png_phase/2,
    convert_png_to_pdf_phase/2
]).

% ============================================================
% Main calculation pipeline (the click(run_calculation) transition body)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:765-785
%%     if st.button("Run Calculation"):
%%         st.write("### MetersetMap usage warning")
%%         st.warning(pymedphys.metersetmap.WARNING_MESSAGE)
%%         st.write("### Calculation status")
%%         run_calculation(reference_results, evaluation_results, gamma_options,
%%                         escan_directory, png_output_directory)
%%
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:437-516 (run_calculation body)
%%     st.write("Calculating Reference MetersetMap...")
%%     reference_metersetmap = calculate_batch_metersetmap(reference_results["deliveries"])
%%     st.write("Calculating Evaluation MetersetMap...")
%%     evaluation_metersetmap = calculate_batch_metersetmap(evaluation_results["deliveries"])
%%     st.write("Calculating Gamma...")
%%     gamma = calculate_gamma(reference_metersetmap, evaluation_metersetmap, gamma_options)
%%     ... build paths, header_text, footer_text ...
%%     fig = plot_and_save_results(...)
%%     fig.tight_layout()
%%     st.write("## Results")
%%     st.pyplot(fig)
%%     st.write("## Saving reports")
%%     st.write("### PNG")
%%     st.write("Saving figure as PNG...")
%%     plt.savefig(png_filepath, dpi=100)
%%     st.write(f"Saved:\n\n`{png_filepath}`")
%%     convert_png_to_pdf(png_filepath, pdf_filepath)
%%
%% Tier progression:
%%   modal_warning_metersetmap_usage    (entered by widget_ops:run_calculation_clicked)
%%   -> computing_reference_metersetmap   (calculate_batch_metersetmap on ref deliveries)
%%   -> computing_evaluation_metersetmap  (same on eval deliveries)
%%   -> computing_gamma                   (calculate_gamma)
%%   -> computing_plot                    (plot_and_save_results -- 4 imageio.imwrite + matplotlib figure)
%%   -> computing_png_save                (plt.savefig)
%%   -> computing_pdf_convert             (subprocess('magick convert' or 'convert'))
%%   -> displaying_results                (st.pyplot + st.markdown(href) + st.write(saved))
%%       OR error_pdf_conversion          (PDF conversion fail; renders UnableToCreatePDF exception)
run_calculation_pipeline(S0, S) :-
    %% Render the modal_warning_metersetmap_usage modal first.
    render_calculation_warning_modal(S0, S1),
    %% Transition to the calculation-status section.
    render_calculation_status('Calculating Reference MetersetMap...', S1, S2),
    S3 = S2.put(tier, computing_reference_metersetmap),
    Reference = S3.compute.reference_results,
    calculate_batch_metersetmap_op(reference, Reference.deliveries, S3, S4),

    render_calculation_status('Calculating Evaluation MetersetMap...', S4, S5),
    S6 = S5.put(tier, computing_evaluation_metersetmap),
    Evaluation = S6.compute.evaluation_results,
    calculate_batch_metersetmap_op(evaluation, Evaluation.deliveries, S6, S7),

    render_calculation_status('Calculating Gamma...', S7, S8),
    S9 = S8.put(tier, computing_gamma),
    calculate_gamma_op(S9, S10),

    render_calculation_status('Creating figure...', S10, S11),
    S12 = S11.put(tier, computing_plot),
    plot_and_save_results_op(S12, S13),

    %% PY:508-509  st.write("## Results"); st.pyplot(fig)
    render_results_section(S13, S14),

    %% PY:511-516  Saving reports / PNG / PDF
    render_save_status('## Saving reports', S14, S15),
    render_save_status('### PNG', S15, S16),
    save_png_phase(S16, S17),

    convert_png_to_pdf_phase(S17, S18),

    %% Final tier: displaying_results unless PDF conversion failed.
    (   S18.compute.pdf_success == false
    ->  S = S18.put(tier, error_pdf_conversion)
    ;   S = S18.put(tier, displaying_results)
    ).

% ============================================================
% Per-batch metersetmap (ref or eval)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:351-357
%%     def calculate_batch_metersetmap(deliveries):
%%         metersetmap = calculate_metersetmap(deliveries[0])
%%         for delivery in deliveries[1::]:
%%             metersetmap = metersetmap + calculate_metersetmap(delivery)
%%         return metersetmap
%%
%% Folds delivery_metersetmap over a list of Delivery objects, summing the
%% resulting metersetmap arrays. Each delivery_metersetmap call is cached
%% (cache_registry: calculate_metersetmap, hash by Delivery: hash); the
%% pipeline emits cache_miss/cache_hit labels per delivery.
%%
%% Internal-trace state computing_per_delivery(Role, I, N) visited per delivery
%% within this fold (not user-receptive).
calculate_batch_metersetmap_op(_Role, [], S, S).
calculate_batch_metersetmap_op(Role, Deliveries, S0, S) :-
    Deliveries = [_|_],
    %% MAX_LEAF_GAP = 410, GRID_RESOLUTION = 1, LEAF_PAIR_WIDTHS = (10,) + (5,) * 78 + (10,)
    %% (PY:45-47). Constants threaded through delivery_metersetmap as kwargs.
    fold_metersetmaps(Role, Deliveries, 0, none, S0, MetersetMap, S1),
    %% Store under the appropriate compute slot.
    (   Role == reference
    ->  C1 = S1.compute.put(reference_metersetmap, MetersetMap)
    ;   C1 = S1.compute.put(evaluation_metersetmap, MetersetMap)
    ),
    S = S1.put(compute, C1).

fold_metersetmaps(_Role, [], _I, Acc, S, Acc, S).
fold_metersetmaps(Role, [Delivery | Rest], I, Acc0, S0, Result, S) :-
    %% Internal-trace state: per-delivery compute
    Tier = computing_per_delivery(Role, I),
    S1 = S0.put(tier, Tier),
    delivery_metersetmap(Delivery, 410, 1, leaf_pair_widths_default, MapI),
    %% Fold: first delivery sets Acc; subsequent deliveries sum
    (   Acc0 == none
    ->  Acc1 = MapI
    ;   Acc1 = MapI   %% In source: `metersetmap + delivery.metersetmap(...)`
                       %% The numerical sum is opaque to the LTS; modeled as
                       %% if delivery_metersetmap returned the partial sum.
    ),
    I1 is I + 1,
    fold_metersetmaps(Role, Rest, I1, Acc1, S1, Result, S).

% ============================================================
% Gamma kernel call
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:453-455
%%     gamma = calculate_gamma(
%%         reference_metersetmap, evaluation_metersetmap, gamma_options
%%     )
%%
%% Cached via cache_registry: calculate_gamma. The kernel call goes through
%% to_tuple (cache_registry: to_tuple) on each metersetmap to make them
%% hashable; that's a separate cache slot.
calculate_gamma_op(S0, S) :-
    Ref = S0.compute.reference_metersetmap,
    Eval = S0.compute.evaluation_metersetmap,
    Opts = S0.compute.gamma_options,
    %% Build a synthetic COORDS pair (PY:53 -- (GRID["jaw"], GRID["mlc"])).
    %% Modeled here as an opaque atom passed to pymedphys_gamma.
    pymedphys_gamma(coords_jaw_mlc, Ref, coords_jaw_mlc, Eval, Opts, Gamma),
    C1 = S0.compute.put(gamma, Gamma),
    S = S0.put(compute, C1).

% ============================================================
% Plot + save results
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:236-339 (plot_and_save_results)
%% Heavy matplotlib + imageio composition. The LTS treats it as a single
%% transition emitting a sequence of side-effect-stream labels:
%%   - imageio.imwrite x 4  (reference.png, evaluation.png, diff.png, gamma.png)
%%   - plt.subplots
%%   - 4 metersetmap_display calls into matplotlib axes
%%   - plot_gamma_hist invocation
%%   - returns a fig handle
plot_and_save_results_op(S0, S) :-
    Reference = S0.compute.reference_results,
    PatientId = Reference.patient_id,
    %% Build paths
    EvalIdentifier = S0.compute.evaluation_results.identifier,
    RefIdentifier = Reference.identifier,
    format(atom(Basename), '~w ~w vs ~w', [PatientId, RefIdentifier, EvalIdentifier]),
    PngOutputDir = S0.widgets.png_output_directory,
    atom_concat(PngOutputDir, '/', Tmp1),
    atom_concat(Tmp1, Basename, RecordDir),
    path_mkdir(RecordDir, true, true),

    %% Save 4 PNGs via imageio.imwrite (PY:257-278)
    write_metersetmap_pngs(S0, RecordDir),

    %% Build the matplotlib figure
    plt_subplots(5, 2, [10, 16], FigAxes),

    %% Render header / footer / 4 main subplots / hist (PY:296-337)
    %% Modeled here as a single fig_handle; the side-effects (axis assignments,
    %% display calls) are emitted via the boundary primitives.
    Ref = S0.compute.reference_metersetmap,
    Eval = S0.compute.evaluation_metersetmap,
    Gamma = S0.compute.gamma,
    metersetmap_display(grid_handle, Ref, 0, 1.0),
    metersetmap_display(grid_handle, Eval, 0, 1.0),
    metersetmap_display(grid_handle, diff_array, -1.0, 1.0),
    metersetmap_display(grid_handle, Gamma, 0, 2),

    C1 = S0.compute.put(_{
        fig_handle: FigAxes,
        png_record_directory: RecordDir
    }),
    S = S0.put(compute, C1).

%% Side-effect: 4 imageio.imwrite calls. Modeled as a pure stream of labels
%% (no further state mutation -- the PNGs land on disk).
write_metersetmap_pngs(_State, _RecordDir) :-
    %% normalize_and_convert_to_uint8 is from algorithm_kernels.pl
    normalize_to_uint8(reference_metersetmap, 0, max_metersetmap, RefImg),
    imageio_write_with_path('reference.png', RefImg),
    normalize_to_uint8(evaluation_metersetmap, 0, max_metersetmap, EvalImg),
    imageio_write_with_path('evaluation.png', EvalImg),
    normalize_to_uint8(diff_metersetmap, neg_max_diff, max_diff, DiffImg),
    imageio_write_with_path('diff.png', DiffImg),
    normalize_to_uint8(gamma_metersetmap, 0, 2, GammaImg),
    imageio_write_with_path('gamma.png', GammaImg).

imageio_write_with_path(_RelPath, _Image).
    %% Boundary: streamlit_boundary:imageio_imwrite (would be wired in a real
    %% Prolog runtime; for the LTS schematic we treat the call as a label).

% ============================================================
% Status check (sidebar button)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:101-138 + helpers :69-98
%%     show_status_indicators(config) -> guarded by st.sidebar.button
%%
%% On click: scans configured iCOM directories (one per linac) and TRF backup
%% directory (one tree, scanned per linac_id). Per linac, finds the most-recent
%% file's mtime, formats with timeago, renders one sidebar markdown line.
%%
%% Two failure modes:
%%   - ConfigMissing (KeyError in get_icom_live_stream_directories or
%%     get_indexed_backups_directory) -> render exception, return.
%%   - No files found in the directory -> render "{linac_id}: `Never`" and
%%     skip that linac.
%%
%% The pipeline transitions through internal-trace states viewing_icom_status
%% then viewing_trf_status, ending in displaying_results (or back into the
%% prior tier if status_check was invoked from a non-init state).
run_status_check_pipeline(S0, S) :-
    %% Try to read the iCOM + TRF config; both may KeyError.
    catch(
        run_status_check_inner(S0, S),
        config_missing(_Reason),
        S = S0.put(tier, error_config_missing)
    ).

run_status_check_inner(S0, S) :-
    S1 = S0.put(tier, viewing_icom_status),
    %% For each configured linac: glob *.txt from icom_directory, find max mtime,
    %% format with timeago, accumulate into sidebar.icom_status_lines.
    %% (Iteration loop omitted for orchestration-first build.)
    accumulate_icom_status_lines(S1, S2),
    S3 = S2.put(tier, viewing_trf_status),
    accumulate_trf_status_lines(S3, S),
    %% Tier intentionally left at viewing_trf_status; the next non-button event
    %% naturally transitions to the appropriate idle tier.
    true.

accumulate_icom_status_lines(S, S).
    %% Stub: in the orchestration-first build, the iteration over linacs is
    %% modeled as a single transition. Real LTS would emit per-linac
    %% path_glob + path_getmtime + render_status_line labels.

accumulate_trf_status_lines(S, S).

% ============================================================
% Advanced debugging (sidebar button, advanced-mode-only)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:373-434 (advanced_debugging)
%%     if st.sidebar.button("Compare Baseline to Output Directory"):
%%         baseline_directory = pathlib.Path(config["debug"]["baseline_directory"]).resolve()
%%         png_baseline_directory = baseline_directory.joinpath("png")
%%         baseline_png_paths = [path for path in png_baseline_directory.rglob("*") if path.is_file()]
%%         relative_png_paths = [path.relative_to(png_baseline_directory) for path in baseline_png_paths]
%%         output_dir = pathlib.Path(config["output"]["png_directory"]).resolve()
%%         evaluation_png_paths = [output_dir.joinpath(path) for path in relative_png_paths]
%%         for baseline, evaluation in zip(baseline_png_paths, evaluation_png_paths):
%%             ...
%%             baseline_image = imageio.imread(baseline)
%%             try:
%%                 evaluation_image = imageio.imread(evaluation)
%%             except FileNotFoundError as e:
%%                 ... render error and return ...
%%             agree = np.allclose(baseline_image, evaluation_image)
%%             st.write(f"Images Agree: `{agree}`")
%%
%% Transitions: comparing_baseline_to_output -> displaying_baseline_diff
%% (or error_file_not_found_baseline on FileNotFoundError mid-loop).
run_advanced_debugging_pipeline(S0, S) :-
    S1 = S0.put(tier, comparing_baseline_to_output),
    %% Iteration body omitted; per file: imageio_imread baseline,
    %% try imageio_imread evaluation (catch FileNotFoundError -> error tier),
    %% np.allclose, render result.
    S = S1.put(tier, displaying_baseline_diff).
