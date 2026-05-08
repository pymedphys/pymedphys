%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Boundary primitives -- every external call the pseudonymise app makes
%% to Streamlit, pydicom, the standard library, or pymedphys's own
%% pseudonymisation API. All bodies fail by default; a test harness mocks
%% them. The DCG and ops modules call these by name.
%%
%% Categories:
%%   - Streamlit widget rendering    (st_*)
%%   - Streamlit page mutation       (st_write, st_text, st_sidebar_markdown)
%%   - DICOM I/O                     (pydicom_*)
%%   - DICOM anonymisation kernel    (anonymise_dataset, pseudonymisation_*)
%%   - ZIP/IO                        (zipfile_*, bytesio_*)
%%   - stdlib (datetime, base64, print)
%%   - Constants/lookups             (sop_class_mode_prefix, default_keywords)

:- module(streamlit_boundary, [
    % ==== Streamlit widget rendering ====
    st_file_uploader/5,             % st_file_uploader(+Label, +Types, +AcceptMulti, +Key, -UploadedFiles)
    st_button/3,                    % st_button(+Label, +Key, -Clicked)

    % ==== Streamlit page mutation (render side) ====
    st_write/1,                     % st_write(+Value)
    st_text/1,                      % st_text(+String)
    st_sidebar_markdown/2,          % st_sidebar_markdown(+HtmlString, +UnsafeAllowHtml)

    % ==== DICOM I/O ====
    pydicom_dcmread/3,              % pydicom_dcmread(+Buffer, +Force, -Dataset)
    pydicom_dcmwrite/2,             % pydicom_dcmwrite(+FileOrBuffer, +Dataset)

    % ==== DICOM anonymisation kernel ====
    anonymise_dataset/6,            % anonymise_dataset(+Ds, +DeletePrivate, +DeleteUnknown, +CopyDataset, +Keywords, +Strategy)
    pseudonymisation_dispatch/3,    % pseudonymisation_dispatch(+VR, +Value, -PseudoValue)
    get_default_pseudonymisation_keywords/1,  % get_default_pseudonymisation_keywords(-Keywords)

    % ==== ZIP / IO ====
    zipfile_open_write/3,           % zipfile_open_write(+Stream, +CompressionFlag, -Handle)
    zipfile_writestr/4,             % zipfile_writestr(+Handle, +Filename, +Bytes, +CompressType)
    zipfile_close/1,                % zipfile_close(+Handle)
    bytesio_new/1,                  % bytesio_new(-Buffer)
    bytesio_getvalue/2,             % bytesio_getvalue(+Buffer, -Bytes)
    bytesio_close/1,                % bytesio_close(+Buffer)

    % ==== stdlib ====
    python_print/1,                 % python_print(+Term)         (stdout, observable to terminal harness)
    datetime_now/1,                 % datetime_now(-DateTime)
    datetime_strftime/3,            % datetime_strftime(+DateTime, +Format, -String)
    base64_b64encode/2,             % base64_b64encode(+Bytes, -B64String)

    % ==== Constants / lookups ====
    sop_class_mode_prefix/2,        % sop_class_mode_prefix(+SopClassName, -Prefix)
    pymedphys_remove_file/1         % pymedphys_remove_file(+Path) -- imported but only referenced in commented-out code
]).

% ============================================================
% Streamlit widget rendering
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:233-237
%%     uploaded_file_buffer_list = st.file_uploader(
%%         "Files to pseudonymise, refresh page after downloading zip(s)",
%%         ["dcm"],
%%         accept_multiple_files=True,
%%     )
%% Note: Streamlit auto-keys this widget by call-site position because no `key=` is supplied.
%% Modeled here with the implicit key `auto_file_uploader_0`.
st_file_uploader(_Label, _Types, _AcceptMulti, _Key, _UploadedFiles) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:239
%%     if st.button("Pseudonymise", key="PseudonymiseButton"):
st_button(_Label, _Key, _Clicked) :- fail.

% ============================================================
% Streamlit page mutation (render side)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:173
%%     st.write(index_to_fifty_mbyte_increment)
st_write(_Value) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:193
%%     st.text("Problem processing DICOM data")
st_text(_String) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:52
%%     st.sidebar.markdown(href, unsafe_allow_html=True)
%% format: HTML <a href="data:file/zip;base64,..."> download links accumulated in the sidebar
st_sidebar_markdown(_HtmlString, _UnsafeAllowHtml) :- fail.

% ============================================================
% DICOM I/O
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:114-116
%%     ds_input: pydicom.FileDataset = pydicom.dcmread(
%%         uploaded_file_buffer, force=True
%%     )
%% format: DICOM (pydicom dcmread; force=True permits non-conformant files)
pydicom_dcmread(_Buffer, _Force, _Dataset) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:129
%%     pydicom.dcmwrite(in_memory_temp_file, ds_input)
%% format: DICOM (pydicom dcmwrite into a BytesIO buffer)
pydicom_dcmwrite(_FileOrBuffer, _Dataset) :- fail.

% ============================================================
% DICOM anonymisation kernel (algorithm boundary)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:118-125
%%     anonymise_dataset(
%%         ds_input,
%%         delete_private_tags=True,
%%         delete_unknown_tags=True,
%%         copy_dataset=False,           # do the work in place
%%         identifying_keywords=keywords,
%%         replacement_strategy=strategy,
%%     )
%% kernel: see python-algorithm-verification/anonymise/ for input/output predicate verification
%%         (DEFERRED -- skill not yet built; algorithm is from pymedphys._dicom.anonymise.api.anonymise_dataset)
%% Note: copy_dataset=False means the dataset is mutated in place; the same in-memory
%% object is later read by pydicom_dcmwrite.
anonymise_dataset(_Ds, _DeletePrivate, _DeleteUnknown, _CopyDataset, _Keywords, _Strategy) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:69-71
%%     pseudo_sop_instance_uid = pseudonymisation_api.pseudonymisation_dispatch[
%%         "UI"
%%     ](ds_input.SOPInstanceUID)
%% Strategy is a per-VR dispatch dict; this call resolves the "UI" (Unique Identifier) entry.
pseudonymisation_dispatch(_VR, _Value, _PseudoValue) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:96
%%     keywords = pseudonymisation_api.get_default_pseudonymisation_keywords()
get_default_pseudonymisation_keywords(_Keywords) :- fail.

% ============================================================
% ZIP / IO
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:101
%%     with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as myzip:
zipfile_open_write(_Stream, _Compression, _Handle) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:135-139
%%     myzip.writestr(
%%         anon_filename,
%%         in_memory_temp_file.getvalue(),
%%         compress_type=ZIP_DEFLATED,
%%     )
%% format: ZIP entry, DEFLATE-compressed
zipfile_writestr(_Handle, _Filename, _Bytes, _CompressType) :- fail.

zipfile_close(_Handle) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:127, :182
%%     in_memory_temp_file = io.BytesIO()       (per-file)
%%     zip_bytes_io = io.BytesIO()              (per-chunk)
bytesio_new(_Buffer) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:137, :196
%%     in_memory_temp_file.getvalue()
%%     zip_bytes_io.getvalue()
bytesio_getvalue(_Buffer, _Bytes) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:140, :189, :197
%%     in_memory_temp_file.close()
%%     zip_bytes_io.close()
bytesio_close(_Buffer) :- fail.

% ============================================================
% Stdlib
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:131-132
%%     print(e_info)
%%     print(f"While processing {original_file_name}")
%% Observable to a headless terminal-running harness; not visible in the browser UI.
%% Included in the alphabet for operational fidelity (per ALGT bisimulation pattern).
python_print(_Term) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:164
%%     my_date_time = datetime.datetime.now()
datetime_now(_DateTime) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:165
%%     str_now_datetime = my_date_time.strftime("%Y%m%d_%H%M%S")
datetime_strftime(_DateTime, _Format, _String) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:48
%%     b64 = base64.b64encode(zip_bytes).decode()
base64_b64encode(_Bytes, _B64String) :- fail.

% ============================================================
% Constants / lookups
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:75
%%     mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[sop_class_uid.name]
%% Imported from pymedphys._dicom.constants.core; deterministic lookup table.
sop_class_mode_prefix(_SopClassName, _Prefix) :- fail.

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:28
%%     from pymedphys._dicom.utilities import remove_file
%% ⚠ Python source quirk preserved verbatim: imported but only referenced inside the
%% commented-out `# if st.button(f"Delete Zip(s)", key="DeleteZip"):` block at lines 244-246.
%% Kept here so the boundary surface mirrors the source's import set.
pymedphys_remove_file(_Path) :- fail.
