%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Session/widget/cache state for the pseudonymise app.
%%
%% Mechanism:    st.session_state + widget-keyed cache + @st.cache_* decorators
%% Persistence:  per-browser-tab Streamlit session (lost on tab close, page refresh,
%%               or st.session_state.clear()).
%% Touched by:   widget_ops:upload_dicom_files, widget_ops:clear_dicom_files,
%%               widget_ops:pseudonymise_button_click,
%%               compute_ops:*, render_ops:*
%%
%% This app uses NO `st.session_state` keys directly. All persistent state is
%% widget-keyed via Streamlit's runtime, plus the in-flight compute-pipeline
%% state-dict slots that the LTS uses to model partial-progress observables.
%% No `@st.cache_data` or `@st.cache_resource` decorators are present in this app.
%%
%% State{} dict shape (top-level fields shown; see bdd_state_dict.svg for schema):
%%
%%   state{
%%     tier:           init | idle_no_files | idle_files_uploaded |
%%                     computing_chunking | computing_per_chunk(I, N) |
%%                     computing_per_file(I, J) | computing_zip_assembled(I) |
%%                     displaying_results | error_bad_data,
%%     session:        _{},                  % no st.session_state usage in this app
%%     widgets:        _{
%%                       dicom_uploader: [UploadedFileList],
%%                       pseudonymise_button: Bool
%%                     },
%%     caches:         _{},                  % no @st.cache_* in this app
%%     compute:        _{                    % in-flight compute pipeline state
%%                       chunks: [Int|...],            % chunk end-indices, mirrors
%%                                                     % `index_to_fifty_mbyte_increment`
%%                       current_chunk: Int,           % outer-loop index in pseudonymise_buffer_list
%%                       current_file:  Int,           % inner-loop index in _zip_pseudo_fifty_mbytes
%%                       chunk_count:   Int,           % length(chunks)
%%                       file_count:    Int,           % length(widgets.dicom_uploader)
%%                       zipfile_basename: Atom,       % e.g. 'Pseudonymised_20260507_143022'
%%                       zip_buffer:    Atom,          % handle to current chunk's BytesIO
%%                       bad_data:      Bool,          % True iff exception caught in chunk loop
%%                       last_exception: term(_)       % preserved for the python_print label
%%                     },
%%     sidebar:        _{
%%                       links: [Html|...]              % accumulated download <a href> snippets,
%%                                                      % rendered via st.sidebar.markdown
%%                     },
%%     main:           _{
%%                       chunk_indices_rendered: Bool,  % `st.write(index_to_fifty_mbyte_increment)`
%%                       error_text_rendered:    Bool   % `st.text("Problem processing DICOM data")`
%%                     },
%%     rerun_count:    Int                              % monotonic; pure trace bookkeeping
%%   }

:- module(session_record, [
    initial_state/1,                % initial_state(-State)
    initial_session/1,              % initial_session(-SessionDict)        (always _{})
    initial_widgets/1,              % initial_widgets(-WidgetsDict)
    initial_caches/1,               % initial_caches(-CachesDict)          (always _{})
    initial_compute/1,              % initial_compute(-ComputeDict)
    initial_sidebar/1,              % initial_sidebar(-SidebarDict)
    initial_main/1                  % initial_main(-MainDict)
]).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:232 -- def main()
initial_state(state{
    tier: init,
    session: Session,
    widgets: Widgets,
    caches: Caches,
    compute: Compute,
    sidebar: Sidebar,
    main: Main,
    rerun_count: 0
}) :-
    initial_session(Session),
    initial_widgets(Widgets),
    initial_caches(Caches),
    initial_compute(Compute),
    initial_sidebar(Sidebar),
    initial_main(Main).

initial_session(_{}).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:233-240
%% Streamlit returns [] (or None pre-rerun) for unfilled file_uploader and False for
%% an unclicked button. Modeled here as the post-first-rerun defaults (i.e. after
%% Streamlit has rendered the widgets but before any user interaction).
initial_widgets(_{
    dicom_uploader: [],
    pseudonymise_button: false
}).

initial_caches(_{}).

initial_compute(_{
    chunks: [],
    current_chunk: 0,
    current_file: 0,
    chunk_count: 0,
    file_count: 0,
    zipfile_basename: '',
    zip_buffer: none,
    bad_data: false,
    last_exception: none
}).

initial_sidebar(_{
    links: []
}).

initial_main(_{
    chunk_indices_rendered: false,
    error_text_rendered: false
}).
