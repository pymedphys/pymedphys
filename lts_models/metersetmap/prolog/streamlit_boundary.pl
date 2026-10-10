%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py + sibling modules
%%
%% Streamlit + stdlib + plotting boundary primitives -- every external call the
%% metersetmap orchestrator (main.py) makes that is NOT a Mosaiq DB query
%% (see mosaiq_boundary.pl) and NOT a numerical algorithm kernel
%% (see algorithm_kernels.pl). All bodies fail by default.
%%
%% Categories:
%%   - Streamlit widget rendering    (st_radio, st_checkbox, st_button, st_selectbox,
%%                                    st_text_input, st_columns, st_file_uploader,
%%                                    st_multiselect, st_pyplot)
%%   - Streamlit page mutation       (st_write, st_markdown, st_warning, st_text)
%%   - Streamlit sidebar             (st_sidebar_*, st_sidebar_empty as overview placeholder)
%%   - Streamlit control flow        (st_stop, st_cache_data_*)
%%   - Filesystem                    (path_glob, path_resolve, path_mkdir, getmtime)
%%   - DICOM/iCOM/TRF I/O            (pydicom_dcmread, lzma_open, file_open)
%%   - Plotting                      (plt_*, imageio_imwrite, imageio_imread)
%%   - Subprocess (PDF generation)   (subprocess_check_call)
%%   - Stdlib                        (datetime_now, datetime_fromtimestamp,
%%                                    timeago_format, base64_b64encode, sys_platform)

:- module(streamlit_boundary, [
    % ==== Streamlit widget rendering ====
    st_radio/4,                     % st_radio(+Label, +Options, +Key, -Selected)
    st_checkbox/3,                  % st_checkbox(+Label, +Key, -Checked)
    st_button/3,                    % st_button(+Label, +Key, -Clicked)
    st_selectbox/4,                 % st_selectbox(+Label, +Options, +Index, -Selected)
    st_text_input/4,                % st_text_input(+Label, +Default, +Key, -Value)
    st_columns/2,                   % st_columns(+N, -Columns)
    st_file_uploader/4,             % st_file_uploader(+Label, +Types, +AcceptMulti, +Key, -Result)
    st_multiselect/5,               % st_multiselect(+Label, +Options, +Default, +Key, -Selected)
    st_pyplot/1,                    % st_pyplot(+Figure)

    % ==== Streamlit page mutation ====
    st_write/1,                     % st_write(+Value)
    st_markdown/2,                  % st_markdown(+String, +UnsafeAllowHtml)
    st_warning/1,                   % st_warning(+Message)
    st_text/1,                      % st_text(+String)

    % ==== Streamlit sidebar ====
    st_sidebar_radio/3,             % st_sidebar_radio(+Label, +Options, -Selected)
    st_sidebar_checkbox/2,          % st_sidebar_checkbox(+Label, -Checked)
    st_sidebar_button/2,            % st_sidebar_button(+Label, -Clicked)
    st_sidebar_markdown/1,          % st_sidebar_markdown(+String)
    st_sidebar_write/1,             % st_sidebar_write(+Value)
    st_sidebar_empty/1,             % st_sidebar_empty(-PlaceholderHandle)
    st_placeholder_markdown/2,      % st_placeholder_markdown(+Handle, +String)

    % ==== Streamlit control flow ====
    st_stop/0,                      % st_stop -- aborts the current rerun

    % ==== Filesystem ====
    path_glob/3,                    % path_glob(+Path, +Pattern, -Filepaths)
    path_resolve/2,                 % path_resolve(+Path, -Resolved)
    path_mkdir/3,                   % path_mkdir(+Path, +ExistOk, +Parents)
    path_getmtime/2,                % path_getmtime(+Path, -Mtime)
    path_is_file/1,                 % path_is_file(+Path)

    % ==== DICOM / iCOM / TRF I/O ====
    pydicom_dcmread/3,              % pydicom_dcmread(+PathOrBuffer, +Force, -Dataset)
    lzma_open_read/2,               % lzma_open_read(+IcomPath, -Contents)
    file_open_read_binary/2,        % file_open_read_binary(+Path, -Bytes)

    % ==== Plotting ====
    plt_subplots/4,                 % plt_subplots(+NRows, +NCols, +FigSize, -FigAxes)
    plt_savefig/2,                  % plt_savefig(+Filepath, +Dpi)
    imageio_imwrite/2,              % imageio_imwrite(+Filepath, +Image)
    imageio_imread/2,               % imageio_imread(+Filepath, -Image)

    % ==== Subprocess (PDF generation) ====
    subprocess_check_call/2,        % subprocess_check_call(+CommandLine, +ShellTrue)

    % ==== Stdlib ====
    datetime_now/1,                 % datetime_now(-DateTime)
    datetime_fromtimestamp/2,       % datetime_fromtimestamp(+Mtime, -DateTime)
    timeago_format/3,               % timeago_format(+Past, +Now, -HumanReadable)
    base64_b64encode/2,             % base64_b64encode(+Bytes, -B64String)
    sys_platform/1                  % sys_platform(-Platform)  ('win32' | 'linux' | ...)
]).

% ============================================================
% Streamlit widget rendering
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:591
%%     config_mode = st.sidebar.radio("Config Mode", options=config_options)
%%     (sidebar variant -- see st_sidebar_radio below)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:47-51
%%     import_method = st.radio("DICOM import method", [FILE_UPLOAD, MONACO_SEARCH], key=...)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:127-131  (Select DICOM Plan)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:179-183  (Select relevant perscription)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:150-154    (TRF import method)
st_radio(_Label, _Options, _Key, _Selected) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:636
%%     advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")
%%     (sidebar variant -- see st_sidebar_checkbox)
st_checkbox(_Label, _Key, _Checked) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:764
%%     if st.button("Run Calculation"):
st_button(_Label, _Key, _Clicked) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:183-187
%%     data_method = st.selectbox("Data Input Method", data_method_options, index=...)
%%     (advanced-mode only)
st_selectbox(_Label, _Options, _DefaultIndex, _Selected) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:747
%%     png_output_directory = pathlib.Path(st.text_input("png output directory", default))
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:100-102 (Patient ID, Monaco search)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:116-118 (Patient ID, advanced)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:181-183
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:51-53
st_text_input(_Label, _Default, _Key, _Value) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:669
%%     ref_col, eval_col = st.columns(2)
st_columns(_N, _Columns) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:54-56  (Upload DICOM RT Plan File)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:157-161  (Upload TRF files, multi)
st_file_uploader(_Label, _Types, _AcceptMulti, _Result) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:165-170 (Select iCOM delivery timestamp(s))
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:213-218  (Select TRF delivery timestamp(s))
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_mosaiq.py:79-81 (Select Mosaiq field id(s))
st_multiselect(_Label, _Options, _Default, _Key, _Selected) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:509
%%     st.pyplot(fig)
st_pyplot(_Figure) :- fail.

% ============================================================
% Streamlit page mutation
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py -- many sites
%%     st.write(...)  -- general-purpose render. Used for headers ("##"), tables,
%%     dicts, exception objects, debug prints, etc. Modeled here as a single
%%     boundary primitive; the specific render-op wrappers in render_ops.pl
%%     give each call site a named effect-stream label.
st_write(_Value) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:551
%%     st.markdown(href, unsafe_allow_html=True)  -- the PDF download link
%% format: HTML <a href="data:file/zip;base64,...">
st_markdown(_String, _UnsafeAllowHtml) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:771
%%     st.warning(pymedphys.metersetmap.WARNING_MESSAGE)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:157
%%     st.warning("While extracting the delivery information ...")
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:90, :103
%%     st.warning("Need Mosaiq access ...", "Searched Mosaiq for an entry ...")
%%
%% Each st.warning call site is a distinct first-class modal state per the
%% python-streamlit-state-model SKILL.md. See ui_state_dcg.pl for the
%% modal_warning_* state alphabet.
st_warning(_Message) :- fail.

st_text(_String) :- fail.

% ============================================================
% Streamlit sidebar
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:591
%%     config_mode = st.sidebar.radio("Config Mode", options=config_options)
st_sidebar_radio(_Label, _Options, _Selected) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:636
%%     advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")
st_sidebar_checkbox(_Label, _Checked) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:102
%%     if st.sidebar.button("Check status of iCOM and backups"):
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:375
%%     if st.sidebar.button("Compare Baseline to Output Directory"):
st_sidebar_button(_Label, _Clicked) :- fail.

%% PY: many sites in main.py -- the Configuration / Overview / Status section headers
st_sidebar_markdown(_String) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:111-116, :76, :87
%%     st.sidebar.write(_exceptions.ConfigMissing(...))
%%     st.sidebar.markdown(f"{linac_id}: `Never`")
st_sidebar_write(_Value) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:57
%%     overview_placeholder = st.sidebar.empty()
%% Returns a placeholder handle that can be populated/replaced later via
%% placeholder.markdown(...). Used for the Reference/Evaluation overview blocks
%% which are reset every rerun (PY:60-64).
st_sidebar_empty(_PlaceholderHandle) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:60-64
%%     overview_placeholder.markdown(f"Patient ID: `{patient_id}`...")
st_placeholder_markdown(_Handle, _String) :- fail.

% ============================================================
% Streamlit control flow
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:164
%%     st.warning("..."); st.write(e); st.stop()
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:214
%%     st.write(_exceptions.InputRequired(...)); st.stop()
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_monaco.py:52
%%     st.stop()
%%
%% st.stop() halts the current rerun without raising an exception. Modeled in
%% the LTS as an explicit terminator transition that lands in an error_* state.
st_stop :- fail.

% ============================================================
% Filesystem
% ============================================================

%% PY: many sites -- e.g.
%%   metersetmap/main.py:91   pathlib.Path(icom_directory).glob("*.txt")
%%   metersetmap/main.py:97   directory.glob("*.zip")
%%   metersetmap/_dicom.py:104   monaco_export_directory.glob(f"{patient_id}_*.dcm")
%%   metersetmap/_icom.py:122-123   path.glob(f"{patient_id}_*/*.xz")
%%   metersetmap/_trf.py:186   indexed_trf_directory.glob(f"*/{patient_id}_*/*/*/*/*.trf")
%%   metersetmap/main.py:389   png_baseline_directory.rglob("*")
path_glob(_Path, _Pattern, _Filepaths) :- fail.

path_resolve(_Path, _Resolved) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:468
%%     png_record_directory.mkdir(exist_ok=True, parents=True)
path_mkdir(_Path, _ExistOk, _Parents) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:74, :79
%%     latest_filepath = max(filepaths, key=os.path.getmtime)
%%     most_recent = datetime.fromtimestamp(os.path.getmtime(latest_filepath))
path_getmtime(_Path, _Mtime) :- fail.

path_is_file(_Path) :- fail.

% ============================================================
% DICOM / iCOM / TRF I/O
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_dicom.py:32, :63
%%     dcm = pydicom.dcmread(str(filepath), force=True, stop_before_pixels=True)
%%     dicom_plan = pydicom.dcmread(dicom_plan_bytes, force=True)
%% format: DICOM (pydicom dcmread; force=True permits non-conformant files)
pydicom_dcmread(_PathOrBuffer, _Force, _Dataset) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_icom.py:29
%%     with lzma.open(icom_path, "r") as f: contents = f.read()
%% format: iCOM stream (LZMA-compressed binary)
lzma_open_read(_IcomPath, _Contents) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_trf.py:289-290
%%     with open(path_or_binary, "rb") as f: trf_contents = f.read()
%% format: TRF (Elekta linac log file, binary)
file_open_read_binary(_Path, _Bytes) :- fail.

% ============================================================
% Plotting (matplotlib + imageio)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:284
%%     fig, axs = plt.subplots(5, 2, figsize=(10, 16), gridspec_kw=gs_kw)
plt_subplots(_NRows, _NCols, _FigSize, _FigAxes) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:514
%%     plt.savefig(png_filepath, dpi=100)
plt_savefig(_Filepath, _Dpi) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:257-278  (4 imwrite calls)
%%     imageio.imwrite(reference_filepath, ...)
%%     imageio.imwrite(evaluation_filepath, ...)
%%     imageio.imwrite(diff_filepath, ...)
%%     imageio.imwrite(gamma_filepath, ...)
%% format: PNG (imageio default)
imageio_imwrite(_Filepath, _Image) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:407, :410
%%     baseline_image = imageio.imread(baseline)
%%     evaluation_image = imageio.imread(evaluation)
imageio_imread(_Filepath, _Image) :- fail.

% ============================================================
% Subprocess (PDF generation)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:524-525
%%     subprocess.check_call(f'magick convert "{png_filepath}" "{pdf_filepath}"', shell=True)
%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:530-531
%%     subprocess.check_call(f'convert "{png_filepath}" "{pdf_filepath}"', shell=True)
%%
%% First tries `magick convert` (ImageMagick 7.x), falls back to `convert`
%% (ImageMagick 6.x). On both fails, renders the UnableToCreatePDF exception.
%% format: PDF (via ImageMagick image-format conversion)
subprocess_check_call(_CommandLine, _ShellTrue) :- fail.

% ============================================================
% Stdlib
% ============================================================

datetime_now(_DateTime) :- fail.

datetime_fromtimestamp(_Mtime, _DateTime) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:85
%%     human_readable = timeago.format(most_recent, now)
timeago_format(_Past, _Now, _HumanReadable) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:545
%%     pdf_b64 = base64.b64encode(pdf_contents).decode()
base64_b64encode(_Bytes, _B64String) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/main.py:554
%%     if sys.platform == "win32":
sys_platform(_Platform) :- fail.
