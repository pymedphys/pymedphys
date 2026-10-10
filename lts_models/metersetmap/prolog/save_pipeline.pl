%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py:511-568
%%
%% The save pipeline -- runs after the gamma+plot computation. Two phases:
%%   PNG save:  plt.savefig(png_filepath, dpi=100)
%%   PDF convert: subprocess.check_call('magick convert ...') with fallback to 'convert'
%%
%% On PDF success: render the download link via st.markdown(href, unsafe_allow_html=True).
%% On PDF fail (both magick and convert missing): render UnableToCreatePDF
%% exception with a platform-specific install URL.

:- module(save_pipeline, [
    save_png_phase/2,                   % save_png_phase(+State0, -State)
    convert_png_to_pdf_phase/2,         % convert_png_to_pdf_phase(+State0, -State)

    save_pipeline_outcome/2             % save_pipeline_outcome(+State, -Outcome)
                                         %   pdf_success_link_emitted | pdf_failure_install_message
]).

:- use_module(streamlit_boundary, [
    plt_savefig/2,
    subprocess_check_call/2,
    sys_platform/1
]).
:- use_module(render_ops, [
    render_save_status/3,
    render_pdf_download_link/3,
    render_unable_to_create_pdf/2
]).

% ============================================================
% PNG save phase
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:513-515
%%     st.write("Saving figure as PNG...")
%%     plt.savefig(png_filepath, dpi=100)
%%     st.write(f"Saved:\n\n`{png_filepath}`")
%%
%% Tier: computing_png_save -> (returns to caller; tier set by caller for next phase)
save_png_phase(S0, S) :-
    S1 = S0.put(tier, computing_png_save),
    PngFilepath = S1.compute.png_filepath,
    %% Synthesise a path if not already set (orchestration-first build doesn't
    %% thread the actual paths from plot_and_save_results_op).
    (   PngFilepath == none
    ->  PngFp = png_filepath_default
    ;   PngFp = PngFilepath
    ),
    plt_savefig(PngFp, 100),
    render_save_status('Saved:', S1, S2),
    C1 = S2.compute.put(png_filepath, PngFp),
    S = S2.put(compute, C1).

% ============================================================
% PDF convert phase (the magick/convert subprocess fallback chain)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:519-568 (convert_png_to_pdf body)
%%     def convert_png_to_pdf(png_filepath, pdf_filepath):
%%         st.write("### PDF")
%%         st.write("Converting PNG to PDF...")
%%         try:
%%             subprocess.check_call(
%%                 f'magick convert "{png_filepath}" "{pdf_filepath}"', shell=True
%%             )
%%             success = True
%%         except subprocess.CalledProcessError:
%%             try:
%%                 subprocess.check_call(
%%                     f'convert "{png_filepath}" "{pdf_filepath}"', shell=True
%%                 )
%%                 success = True
%%             except subprocess.CalledProcessError:
%%                 success = False
%%
%%         if success:
%%             ... emit download link ...
%%         else:
%%             ... emit UnableToCreatePDF ...
%%
%% Tier: computing_pdf_convert -> displaying_results | error_pdf_conversion
%%
%% The two-step fallback (magick -> convert) handles ImageMagick 7 vs 6 install
%% differences. Both shell=True; the command construction is verbatim from
%% PY:524-525 and PY:530-531.
convert_png_to_pdf_phase(S0, S) :-
    S1 = S0.put(tier, computing_pdf_convert),
    render_save_status('### PDF', S1, S2),
    render_save_status('Converting PNG to PDF...', S2, S3),

    PngFp = S3.compute.png_filepath,
    PdfFp = S3.compute.pdf_filepath,
    (   PdfFp == none
    ->  Pdf = pdf_filepath_default
    ;   Pdf = PdfFp
    ),

    %% Try magick (ImageMagick 7).
    catch(
        (   format(atom(Cmd1), 'magick convert "~w" "~w"', [PngFp, Pdf]),
            subprocess_check_call(Cmd1, true),
            Success = true
        ),
        _Err1,
        %% Fallback to convert (ImageMagick 6).
        catch(
            (   format(atom(Cmd2), 'convert "~w" "~w"', [PngFp, Pdf]),
                subprocess_check_call(Cmd2, true),
                Success = true
            ),
            _Err2,
            Success = false
        )
    ),

    C1 = S3.compute.put(_{
        pdf_filepath: Pdf,
        pdf_success: Success
    }),
    S4 = S3.put(compute, C1),

    %% Branch on success.
    (   Success == true
    ->  render_save_status('Created:', S4, S5),
        render_pdf_download_link(Pdf, S5, S)
    ;   render_unable_to_create_pdf(S4, S)
    ).

% ============================================================
% Outcome classifier
% ============================================================

save_pipeline_outcome(State, pdf_success_link_emitted) :-
    State.compute.pdf_success == true.
save_pipeline_outcome(State, pdf_failure_install_message) :-
    State.compute.pdf_success == false.
