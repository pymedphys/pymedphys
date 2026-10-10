%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Render-side operations -- the predicates that emit page-mutation labels into
%% the side-effect stream. Each render_op wraps a single boundary primitive
%% (st.write, st.text, st.sidebar.markdown) and updates the corresponding
%% slot in `state.main` or `state.sidebar` so the LTS can reason about
%% "what got drawn" as labeled effect.

:- module(render_ops, [
    render_chunk_indices/2,         % render_chunk_indices(+State0, -State)
    render_download_link/4,         % render_download_link(+ZipName, +ZipBytes, +State0, -State)
    render_error_text/2,            % render_error_text(+State0, -State)
    print_exception_label/3         % print_exception_label(+OriginalFilename, +State0, -State)
]).

:- use_module(streamlit_boundary, [
    st_write/1,
    st_text/1,
    st_sidebar_markdown/2,
    base64_b64encode/2,
    python_print/1
]).

% ============================================================
% Main-page renders
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:173
%%     st.write(index_to_fifty_mbyte_increment)
%% Renders the chunk-index list as a Python list-repr to the main page.
render_chunk_indices(S0, S) :-
    Indices = S0.compute.chunks,
    st_write(Indices),
    M1 = S0.main.put(chunk_indices_rendered, true),
    S = S0.put(main, M1).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:193
%%     st.text("Problem processing DICOM data")
%% Note the literal string; not parameterised on the exception. The user sees
%% the same text regardless of which file or which exception type triggered.
render_error_text(S0, S) :-
    st_text('Problem processing DICOM data'),
    M1 = S0.main.put(error_text_rendered, true),
    S = S0.put(main, M1).

% ============================================================
% Sidebar download-link emission
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:36-52, called from :196
%%     def link_to_zipbuffer_download(filename, zip_bytes):
%%         b64 = base64.b64encode(zip_bytes).decode()
%%         href = f"<a href=\"data:file/zip;base64,{b64}\" download='{filename}'>\
%%             Click to download {filename}\
%%         </a>"
%%         st.sidebar.markdown(href, unsafe_allow_html=True)
%%
%% format: HTML <a href="data:file/zip;base64,..."> appended to sidebar
%% Note the unsafe_allow_html=True flag -- required for the raw <a> tag to render.
%% The 50MByte chunking limit at chunk_index_list:fifty_mbyte_threshold/1 exists
%% specifically because of the data: URL size limit on this download mechanism.
render_download_link(ZipName, ZipBytes, S0, S) :-
    base64_b64encode(ZipBytes, B64),
    format(atom(Href),
        '<a href="data:file/zip;base64,~w" download=\'~w\'>            Click to download ~w        </a>',
        [B64, ZipName, ZipName]),
    st_sidebar_markdown(Href, true),
    Links0 = S0.sidebar.links,
    append(Links0, [Href], Links1),
    Sidebar1 = S0.sidebar.put(links, Links1),
    S = S0.put(sidebar, Sidebar1).

% ============================================================
% Exception print (stdout, not Streamlit DOM)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:131-132
%%     print(e_info)
%%     print(f"While processing {original_file_name}")
%%
%% Two stdout lines per exception:
%%   1. The exception object's repr
%%   2. A "While processing <filename>" context line
%%
%% Observable to a headless terminal-running harness (pytest, docker logs)
%% but NOT to a browser-running Streamlit user. Included in the alphabet
%% per the SKILL.md operational-fidelity rule -- the bisimulation must hold
%% for trace-level test harnesses, not just the browser observer.
print_exception_label(OriginalFilename, S0, S0) :-
    LastException = S0.compute.last_exception,
    %% LastException may be `none` if called pre-catch; the boundary call is
    %% emitted unconditionally to mirror the `print(e_info)` line which fires
    %% even when e_info is empty.
    python_print(LastException),
    format(atom(ContextLine), 'While processing ~w', [OriginalFilename]),
    python_print(ContextLine).
