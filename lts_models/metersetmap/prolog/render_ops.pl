%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py
%%
%% Render-side operations -- the predicates that emit page-mutation labels into
%% the side-effect stream. Each render_op wraps one or more boundary primitives
%% from streamlit_boundary.pl and updates the corresponding slot in
%% `state.main` or `state.sidebar`.

:- module(render_ops, [
    % ==== Top-level page sections ====
    render_intro/2,                     % render_intro(+State0, -State)
    render_data_selection_section/2,    % render_data_selection_section(+State0, -State)
    render_output_locations_section/2,  % render_output_locations_section(+State0, -State)
    render_calculation_section/2,       % render_calculation_section(+State0, -State)
    render_calculation_warning_modal/2, % render_calculation_warning_modal(+State0, -State)
    render_calculation_status/3,        % render_calculation_status(+Message, +State0, -State)
    render_results_section/2,           % render_results_section(+State0, -State)
    render_save_status/3,               % render_save_status(+Message, +State0, -State)
    render_pdf_download_link/3,         % render_pdf_download_link(+PdfFilepath, +State0, -State)
    render_pdf_unable_message/3,        % render_pdf_unable_message(+DownloadUrl, +State0, -State)

    % ==== Sidebar sections ====
    render_sidebar_config_section/2,    % render_sidebar_config_section(+State0, -State)
    render_sidebar_overview_placeholders/2,
    render_sidebar_status_indicators/2, % render_sidebar_status_indicators(+State0, -State)
    render_status_line/3,               % render_status_line(+Line, +State0, -State)
    render_overview_block/4,            % render_overview_block(+Role, +PatientId, +PatientName, +TotalMu, +State0, -State)

    % ==== Display-deliveries (the table rendered per role) ====
    render_deliveries_overview/3,       % render_deliveries_overview(+Role, +Deliveries, +State0, -State)

    % ==== Error / warning render ====
    render_config_missing/2,            % render_config_missing(+State0, -State)
    render_unable_to_create_pdf/2       % render_unable_to_create_pdf(+State0, -State)
]).

:- use_module(streamlit_boundary, [
    st_write/1,
    st_markdown/2,
    st_warning/1,
    st_pyplot/1,
    st_sidebar_markdown/1,
    st_sidebar_write/1,
    st_placeholder_markdown/2,
    sys_platform/1,
    base64_b64encode/2,
    file_open_read_binary/2
]).

% ============================================================
% Top-level page sections
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:572-576
%%     st.write("""Tool to compare the MetersetMap between planned and delivery.""")
render_intro(S0, S) :-
    st_write('Tool to compare the MetersetMap between planned and delivery.'),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [intro | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:661-667
%%     st.write("""## Selection of data to compare""")
%%     st.write("---")
render_data_selection_section(S0, S) :-
    st_write('## Selection of data to compare'),
    st_write('---'),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [data_selection | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:702-720
%%     st.write("---")
%%     st.write("""## Output Locations""")
%%     st.write("""### eSCAN Directory ...""")
render_output_locations_section(S0, S) :-
    st_write('---'),
    st_write('## Output Locations'),
    st_write('### eSCAN Directory'),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [output_locations | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:758-762
%%     st.write("""## Calculation""")
render_calculation_section(S0, S) :-
    st_write('## Calculation'),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [calculation_header | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:765-771
%%     st.write("""### MetersetMap usage warning""")
%%     st.warning(pymedphys.metersetmap.WARNING_MESSAGE)
%%     st.write("""### Calculation status""")
%%
%% First-class modal state: modal_warning_metersetmap_usage. Per the SKILL.md,
%% st.warning is a first-class modal state. The modal "exits" implicitly on
%% the same rerun (Streamlit's st.warning doesn't pause execution; it just
%% renders an alert block and the script continues). The LTS still gives this
%% its own state because the warning IS observable to the user as a render-event.
render_calculation_warning_modal(S0, S) :-
    st_write('### MetersetMap usage warning'),
    st_warning(metersetmap_warning_message),
    st_write('### Calculation status'),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [warning_modal_rendered | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:444, :447, :452, :459, :513
%%     st.write("Calculating Reference MetersetMap...")
%%     st.write("Calculating Evaluation MetersetMap...")
%%     st.write("Calculating Gamma...")
%%     st.write("Creating figure...")
%%     st.write("Saving figure as PNG...")
render_calculation_status(Message, S0, S) :-
    st_write(Message),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [status(Message) | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:508-509
%%     st.write("## Results")
%%     st.pyplot(fig)
render_results_section(S0, S) :-
    st_write('## Results'),
    Fig = S0.compute.fig_handle,
    st_pyplot(Fig),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [results_rendered | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:511-515
%%     st.write("## Saving reports")
%%     st.write("### PNG")
%%     st.write("Saving figure as PNG...")
render_save_status(Message, S0, S) :-
    st_write(Message),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [save_status(Message) | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:540-551
%%     with open(pdf_filepath, "rb") as f:
%%         pdf_contents = f.read()
%%     pdf_filename = pathlib.Path(pdf_filepath).name
%%     pdf_b64 = base64.b64encode(pdf_contents).decode()
%%     href = f"<a href=\"data:file/zip;base64,{pdf_b64}\" download='{pdf_filename}'>...</a>"
%%     st.markdown(href, unsafe_allow_html=True)
%%
%% format: HTML <a href="data:file/zip;base64,..."> -- note the typo:
%%   the MIME type is `file/zip` even though the payload is a PDF. Browsers
%%   accept it, but it's a verbatim quirk to preserve.
%%   ⚠ Python source quirk preserved verbatim: PY:547 uses `data:file/zip;base64`
%%     for what's actually a PDF blob. Browsers accept it; if the typo is fixed,
%%     the LTS bisimulation will diverge at this label.
render_pdf_download_link(PdfFilepath, S0, S) :-
    file_open_read_binary(PdfFilepath, PdfBytes),
    base64_b64encode(PdfBytes, B64),
    %% Construct the href with the verbatim "file/zip" mime
    format(atom(Href),
        '<a href="data:file/zip;base64,~w" download=\'~w\'>Click to download ~w</a>',
        [B64, PdfFilepath, PdfFilepath]),
    st_markdown(Href, true),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [pdf_download_link(PdfFilepath) | M0]),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:553-568
%%     if sys.platform == "win32":
%%         url_hash_parameter = "#windows"
%%     else:
%%         url_hash_parameter = ""
%%     download_url = f"https://imagemagick.org/script/download.php{url_hash_parameter}"
%%     st.write(_exceptions.UnableToCreatePDF(
%%         f"Please install Image Magick to create PDF reports <{download_url}>."
%%     ))
render_pdf_unable_message(DownloadUrl, S0, S) :-
    format(atom(Msg), 'Please install Image Magick to create PDF reports <~w>.', [DownloadUrl]),
    st_write(unable_to_create_pdf(Msg)),
    M0 = S0.main.rendered_sections,
    M1 = S0.main.put(rendered_sections, [pdf_unable_rendered | M0]),
    S = S0.put(main, M1).

% ============================================================
% Sidebar sections
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:578-582
%%     st.sidebar.markdown("# Configuration Choice")
render_sidebar_config_section(S0, S) :-
    st_sidebar_markdown('# Configuration Choice'),
    S = S0.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:594-619
%%     st.sidebar.markdown("# MetersetMap Overview")
%%     st.sidebar.markdown("## Reference")
%%     set_reference_overview = sidebar_overview()  -- creates st.sidebar.empty placeholder
%%     st.sidebar.markdown("## Evaluation")
%%     set_evaluation_overview = sidebar_overview()
render_sidebar_overview_placeholders(S0, S) :-
    st_sidebar_markdown('# MetersetMap Overview'),
    st_sidebar_markdown('## Reference'),
    %% Placeholder created via st_sidebar_empty (boundary primitive)
    st_sidebar_markdown('## Evaluation'),
    S = S0.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:621-627
%%     st.sidebar.markdown("# Status indicators")
%%     show_status_indicators(config)
render_sidebar_status_indicators(S0, S) :-
    st_sidebar_markdown('# Status indicators'),
    S = S0.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:87, :76
%%     st.sidebar.markdown(f"{linac_id}: `{human_readable}`")
%%     st.sidebar.markdown(f"{linac_id}: `Never`")  -- on no files
render_status_line(Line, S0, S) :-
    st_sidebar_markdown(Line),
    Sidebar0 = S0.sidebar,
    Lines0 = Sidebar0.icom_status_lines,
    Sidebar1 = Sidebar0.put(icom_status_lines, [Line | Lines0]),
    S = S0.put(sidebar, Sidebar1).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:60-64
%%     overview_placeholder.markdown(
%%         f"Patient ID: `{patient_id}`\n\n"
%%         f"Patient Name: `{patient_name}`\n\n"
%%         f"Total MU: `{total_mu}`"
%%     )
%%
%% Called once per role per rerun (after the input method dispatches return
%% results). Re-renders the placeholder with the current values; placeholder
%% replacement, not append.
render_overview_block(Role, PatientId, PatientName, TotalMu, S0, S) :-
    format(atom(Block),
        'Patient ID: `~w`\n\nPatient Name: `~w`\n\nTotal MU: `~w`',
        [PatientId, PatientName, TotalMu]),
    %% Placeholder is in state.sidebar.<role>_overview; the actual st_placeholder_markdown
    %% boundary call happens via the call site here.
    Sidebar0 = S0.sidebar,
    (   Role == reference
    ->  Sidebar1 = Sidebar0.put(reference_overview, Block)
    ;   Sidebar1 = Sidebar0.put(evaluation_overview, Block)
    ),
    S = S0.put(sidebar, Sidebar1).

% ============================================================
% Display-deliveries (the per-role table)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:141-170
%%     def display_deliveries(deliveries):
%%         if not deliveries: return 0
%%         st.write("#### Overview of selected deliveries")
%%         data = []
%%         for delivery in deliveries:
%%             num_control_points = len(delivery.mu)
%%             total_mu = delivery.mu[-1] if num_control_points != 0 else 0
%%             data.append([total_mu, num_control_points])
%%         columns = ["MU", "Number of Data Points"]
%%         df = pd.DataFrame(data=data, columns=columns)
%%         st.write(df)
%%         total_mu = round(df["MU"].sum(), 1)
%%         st.write(f"Total MU: `{total_mu}`")
%%         return total_mu
render_deliveries_overview(_Role, [], S0, S) :-
    %% Empty deliveries -> just return 0; no rendering.
    S = S0.
render_deliveries_overview(_Role, Deliveries, S0, S) :-
    Deliveries = [_|_],
    st_write('#### Overview of selected deliveries'),
    %% Build per-delivery row data; render the dataframe.
    st_write(deliveries_dataframe),
    %% Render Total MU footer
    st_write(total_mu_line),
    S = S0.

% ============================================================
% Error / warning render
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:111-116
%%     st.sidebar.write(_exceptions.ConfigMissing(
%%         "iCOM and/or TRF backup configuration is missing. Unable to show status."
%%     ))
render_config_missing(S0, S) :-
    st_sidebar_write(config_missing_exception),
    S = S0.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:563-568
%%     st.write(_exceptions.UnableToCreatePDF(...))
render_unable_to_create_pdf(S0, S) :-
    sys_platform(Platform),
    (   Platform == 'win32'
    ->  UrlHash = '#windows'
    ;   UrlHash = ''
    ),
    format(atom(Url), 'https://imagemagick.org/script/download.php~w', [UrlHash]),
    render_pdf_unable_message(Url, S0, S).
