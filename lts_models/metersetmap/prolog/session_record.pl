%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py + sibling modules
%%
%% Session/widget/cache state for the metersetmap app.
%%
%% Mechanism:    st.session_state (NONE used directly by metersetmap)
%%             + widget-keyed cache (heavy use; keys built via
%%               f"{key_namespace}_<role>" for ref/eval mirroring)
%%             + 13 @st.cache_data slots (see cache_registry.pl)
%% Persistence:  per-browser-tab Streamlit session.
%% Touched by:   widget_ops:*, compute_ops:*, render_ops:*, save_pipeline:*,
%%               and the 5 input_method_stubs:*_phase ops.
%%
%% Like pseudonymise, metersetmap uses NO `st.session_state` keys directly;
%% all persistent state is in widget-keyed cache + @st.cache_data slots. The
%% LTS additionally tracks `compute` and the rendered DOM accumulators for
%% trace fidelity.
%%
%% State{} dict shape (top-level slots; see bdd_state_dict.svg for full schema):
%%
%%   state{
%%     tier:              Tier,
%%     session:           _{},                       % no st.session_state usage
%%     widgets:           _{
%%                          % Sidebar-driven widgets
%%                          config_mode: Atom,             % radio('Config Mode', ...)
%%                          advanced_mode: Bool,           % checkbox('Run in Advanced Mode')
%%                          status_check_button: Bool,     % edge-trigger
%%                          compare_baseline_button: Bool, % edge-trigger (advanced only)
%%
%%                          % Reference column
%%                          reference: input_method_widgets,
%%                          % Evaluation column
%%                          evaluation: input_method_widgets,
%%
%%                          % Output config
%%                          escan_site: Atom,
%%                          png_output_directory: Atom,    % advanced only -- text_input
%%
%%                          % Calculation trigger
%%                          run_calculation_button: Bool   % edge-trigger
%%                        },
%%     caches:            _{ ... },                  % populated by cache_registry
%%     compute:           _{
%%                          reference_results: ResultsDict | none,
%%                          evaluation_results: ResultsDict | none,
%%                          gamma_options: GammaOptionsDict,
%%                          reference_metersetmap: Array | none,
%%                          evaluation_metersetmap: Array | none,
%%                          gamma: Array | none,
%%                          fig_handle: Term | none,
%%                          png_record_directory: Path | none,
%%                          pdf_filepath: Atom | none,
%%                          png_filepath: Atom | none,
%%                          pdf_success: Bool | none
%%                        },
%%     sidebar:           _{
%%                          reference_overview: HtmlString,    % patient_id/name/total_mu block
%%                          evaluation_overview: HtmlString,
%%                          icom_status_lines: List[String],   % from `Check status` button
%%                          trf_status_lines: List[String]
%%                        },
%%     main:              _{
%%                          rendered_sections: List[Atom]      % markers for each top-level
%%                                                             % "## Selection of data ..."
%%                                                             % "## Output Locations"
%%                                                             % "## Calculation"
%%                                                             % "### Calculation status"
%%                                                             % "## Results"
%%                                                             % "## Saving reports" / "### PNG" / "### PDF"
%%                        },
%%     rerun_count:       Int
%%   }
%%
%% `input_method_widgets` is a per-namespace ('reference' or 'evaluation') sub-dict
%% containing the union of all 5 input methods' widget-keyed values. Most are
%% `_unset` for the input method not currently selected; this is intentional
%% mirror of Streamlit's actual widget-state behavior (widgets keyed in one
%% rerun's path retain their values even when another path is taken next rerun).

:- module(session_record, [
    initial_state/1,                % initial_state(-State)
    initial_session/1,              % initial_session(-SessionDict)         (always _{})
    initial_widgets/1,              % initial_widgets(-WidgetsDict)
    initial_compute/1,              % initial_compute(-ComputeDict)
    initial_sidebar/1,              % initial_sidebar(-SidebarDict)
    initial_main/1,                 % initial_main(-MainDict)
    initial_input_method_widgets/1  % initial_input_method_widgets(-Dict)
]).

:- use_module(cache_registry, [initial_caches/1]).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:571 -- def main()
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

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:578-700  (widgets rendered top-to-bottom)
initial_widgets(_{
    config_mode: _unset,
    advanced_mode: false,
    status_check_button: false,
    compare_baseline_button: false,
    reference: ReferenceWidgets,
    evaluation: EvaluationWidgets,
    escan_site: _unset,
    png_output_directory: _unset,
    run_calculation_button: false
}) :-
    initial_input_method_widgets(ReferenceWidgets),
    initial_input_method_widgets(EvaluationWidgets).

%% Per-namespace input-method widget cache. All slots default to _unset; populated
%% only when the user navigates the corresponding input-method sub-LTS.
%% Keys mirror the Streamlit widget keys exactly (with `{key_namespace}_` prefix
%% stripped for clarity; the namespace is the dict key in `widgets.reference`/
%% `widgets.evaluation`).
initial_input_method_widgets(_{
    % Top-level method selectbox (advanced-mode only)
    data_method: _unset,                        % main.py:183-187

    % DICOM sub-LTS widgets
    dicom_file_import_method: _unset,           % _dicom.py:50  (FILE_UPLOAD | MONACO_SEARCH)
    dicom_plan_uploader: none,                  % _dicom.py:55  (FILE_UPLOAD path)
    monaco_site: _unset,                        % _dicom.py:90-95  (MONACO_SEARCH path)
    patient_id: '',                             % _dicom.py, _icom.py, _trf.py, _mosaiq.py
    select_monaco_export_plan: _unset,          % _dicom.py:127-131
    dicom_perscription_chooser: _unset,         % _dicom.py:179-183

    % iCOM sub-LTS widgets
    icom_deliveries: [],                        % _icom.py:165-170 (multiselect)

    % TRF sub-LTS widgets
    trf_file_import_method: _unset,             % _trf.py:153 (FILE_UPLOAD | INDEXED_TRF_SEARCH)
    trf_file_uploader: [],                      % _trf.py:159 (FILE_UPLOAD)
    trf_deliveries: [],                         % _trf.py:217 (multiselect)

    % Mosaiq sub-LTS widgets
    mosaiq_site: _unset,                        % _mosaiq.py:39
    mosaiq_field_id: []                         % _mosaiq.py:80 (multiselect)
}).

%% Compute slot starts empty; populated by compute_ops:run_calculation_pipeline/2
%% during the click(run_calculation_button) transition.
initial_compute(_{
    reference_results: none,
    evaluation_results: none,
    gamma_options: _{
        dose_percent_threshold: 2,
        distance_mm_threshold: 0.5,
        local_gamma: true
        %% Defaults from _config.get_gamma_options when advanced_mode is false;
        %% advanced_mode allows the user to change these (not modeled here in
        %% the orchestration-first build).
    },
    reference_metersetmap: none,
    evaluation_metersetmap: none,
    gamma: none,
    fig_handle: none,
    png_record_directory: none,
    pdf_filepath: none,
    png_filepath: none,
    pdf_success: none
}).

%% Sidebar accumulators -- the overview placeholders are written to once per rerun
%% via st_placeholder_markdown (see streamlit_boundary.pl). The icom/trf status
%% lines accumulate when the user clicks the `Check status` button.
initial_sidebar(_{
    reference_overview: '',
    evaluation_overview: '',
    icom_status_lines: [],
    trf_status_lines: []
}).

%% Main page section markers -- which top-level "## ..." headers have been rendered.
%% Used by browse_ops:displaying_state/1 and family.
initial_main(_{
    rendered_sections: []
}).
