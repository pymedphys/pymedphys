%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Compute-pipeline ops -- the work that runs between the Pseudonymise button
%% click and the final render. Mirrors:
%%
%%   pseudonymise_buffer_list      (PY:144-198)  -- top-level orchestration
%%   _gen_index_list_to_fifty_mbyte_increment   (PY:201-229)  -- chunk indices
%%   _zip_pseudo_fifty_mbytes      (PY:81-141)   -- per-chunk zip + per-file pseudonymise
%%   build_pseudonymised_file_name (PY:55-78)    -- output filename derivation
%%
%% This module emits the side-effect-stream labels (boundary calls into
%% streamlit_boundary.pl) that interleave with the internal-trace state
%% progression. The labels are returned as a list in the State.compute.trace
%% slot so the DCG can attach them to the corresponding step//2 transition.
%%
%% Note: in this LTS we collapse the entire compute pipeline (chunking + per-chunk
%% loop + per-file loop + render) into a single transition between user-receptive
%% states (idle_files_uploaded -> displaying_results | error_bad_data), per the
%% two-tier state model in the SKILL.md. The internal-trace states are visited
%% sequentially within the transition; the activity diagram act_compute_pipeline.svg
%% shows the decomposition.

:- module(compute_ops, [
    run_pseudonymise_pipeline/2,    % run_pseudonymise_pipeline(+State0, -State)
    gen_chunk_indices/2,            % gen_chunk_indices(+State0, -State)
    process_chunk/3,                % process_chunk(+ChunkIndex, +State0, -State)
    pseudonymise_one_file/4,        % pseudonymise_one_file(+File, +ZipHandle, +State0, -State)
    build_pseudonymised_filename/3  % build_pseudonymised_filename(+Dataset, +State0, -Filename)
]).

:- use_module(streamlit_boundary, [
    pydicom_dcmread/3,
    pydicom_dcmwrite/2,
    anonymise_dataset/6,
    pseudonymisation_dispatch/3,
    get_default_pseudonymisation_keywords/1,
    sop_class_mode_prefix/2,
    zipfile_open_write/3,
    zipfile_writestr/4,
    zipfile_close/1,
    bytesio_new/1,
    bytesio_getvalue/2,
    bytesio_close/1,
    datetime_now/1,
    datetime_strftime/3,
    base64_b64encode/2,
    python_print/1
]).
:- use_module(chunk_index_list, [
    compute_chunks/2,
    chunk_count/2,
    next_chunk_bounds/4
]).
:- use_module(uploaded_file_list, [slice_uploaded_files/4]).
:- use_module(render_ops, [
    render_chunk_indices/2,
    render_download_link/3,
    render_error_text/2,
    print_exception_label/3
]).

% ============================================================
% Top-level pipeline orchestration
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:144-198
%%     def pseudonymise_buffer_list(file_buffer_list: list):
%%         if file_buffer_list is not None and len(file_buffer_list) > 0:
%%             my_date_time = datetime.datetime.now()
%%             str_now_datetime = my_date_time.strftime("%Y%m%d_%H%M%S")
%%             zipfile_basename = f"Pseudonymised_{str_now_datetime}"
%%             ...
%%             index_to_fifty_mbyte_increment = _gen_index_list_to_fifty_mbyte_increment(...)
%%             st.write(index_to_fifty_mbyte_increment)
%%             zip_count = 0
%%             start_index = 0
%%             for end_index in index_to_fifty_mbyte_increment:
%%                 if start_index == end_index:
%%                     break
%%                 ...
%%                 bad_data = _zip_pseudo_fifty_mbytes(file_buffer_list[start_index:end_index], zip_bytes_io)
%%                 start_index = end_index
%%                 if bad_data:
%%                     st.text("Problem processing DICOM data")
%%                 else:
%%                     link_to_zipbuffer_download(zipfile_name, zip_bytes_io.getvalue())
%%
%% The LTS walks the chunk list, calling process_chunk/3 for each. After the
%% loop, the tier is set to displaying_results (if no chunk had bad_data) or
%% error_bad_data (if any chunk hit the exception branch).
run_pseudonymise_pipeline(S0, S) :-
    %% PY:164-166: timestamp the basename
    datetime_now(DT),
    datetime_strftime(DT, '%Y%m%d_%H%M%S', Stamp),
    atom_concat('Pseudonymised_', Stamp, Basename),
    C1 = S0.compute.put(zipfile_basename, Basename),
    S1 = S0.put(compute, C1),
    %% PY:169-171: chunk-index computation -- internal-trace state
    S2 = S1.put(tier, computing_chunking),
    gen_chunk_indices(S2, S3),
    %% PY:173: render the chunk-index list to the main page
    render_chunk_indices(S3, S4),
    %% PY:177-198: outer for-loop over chunks
    chunk_count(S4.compute.chunks, N),
    process_chunks_loop(0, N, S4, S5),
    %% Final tier: displaying_results unless any chunk bad_data was set
    (   S5.compute.bad_data == true
    ->  S = S5.put(tier, error_bad_data)
    ;   S = S5.put(tier, displaying_results)
    ).

%% process_chunks_loop(+CurrentIdx, +N, +State0, -State)
process_chunks_loop(N, N, S, S) :- !.
process_chunks_loop(I, N, S0, S) :-
    I < N,
    process_chunk(I, S0, S1),
    %% PY:187-189: if bad_data, break out of the loop. Mirrored here as an
    %% explicit guard rather than a nondeterministic cut so the bisimulation
    %% is exact.
    (   S1.compute.bad_data == true
    ->  S = S1
    ;   I1 is I + 1,
        process_chunks_loop(I1, N, S1, S)
    ).

% ============================================================
% Chunk-index computation
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:169-171
%%     index_to_fifty_mbyte_increment = _gen_index_list_to_fifty_mbyte_increment(
%%         file_buffer_list
%%     )
gen_chunk_indices(S0, S) :-
    Files = S0.widgets.dicom_uploader,
    compute_chunks(Files, EndIndices),
    chunk_count(EndIndices, N),
    C1 = S0.compute.put(_{
        chunks: EndIndices,
        chunk_count: N
    }),
    S = S0.put(compute, C1).

% ============================================================
% Per-chunk processing
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:177-198 (outer loop body) and
%%     :81-141 (the _zip_pseudo_fifty_mbytes helper called per chunk)
%%
%% PY:178-179 -- the `if start_index == end_index: break` guard. This fires when
%% the loop hits a degenerate empty chunk; in practice it can only happen if
%% _gen_index_list_to_fifty_mbyte_increment returns a 0 as its first entry,
%% which is impossible by construction (the inner loop always increments
%% file_count before checking the threshold). Preserved for fidelity.
process_chunk(I, S0, S) :-
    EndIndices = S0.compute.chunks,
    next_chunk_bounds(EndIndices, I, Start, End),
    (   Start == End
    ->  S = S0   %% PY:178-179: break-equivalent (degenerate chunk)
    ;   process_chunk_inner(I, Start, End, S0, S)
    ).

process_chunk_inner(I, Start, End, S0, S) :-
    %% Internal-trace state: entering per-chunk
    Tier = computing_per_chunk(I, S0.compute.chunk_count),
    Files = S0.widgets.dicom_uploader,
    slice_uploaded_files(Start, End, Files, ChunkFiles),
    %% PY:182: zip_bytes_io = io.BytesIO()
    bytesio_new(ZipBuffer),
    %% PY:101: with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as myzip:
    zipfile_open_write(ZipBuffer, deflate, ZipHandle),
    C1 = S0.compute.put(_{current_chunk: I, current_file: 0, zip_buffer: ZipBuffer}),
    S1 = S0.put(_{tier: Tier, compute: C1}),
    %% Inner loop over files in chunk
    process_files_loop(ChunkFiles, 0, ZipHandle, S1, S2),
    %% Close the zip handle (whether bad_data or not, the with-statement closes)
    zipfile_close(ZipHandle),
    %% PY:187-198: branch on bad_data
    (   S2.compute.bad_data == true
    ->  %% PY:188-193: bad_data branch -- close buffer, render error text
        bytesio_close(ZipBuffer),
        render_error_text(S2, S)
    ;   %% PY:195-198: success branch -- internal-trace zip_assembled, then emit link
        Tier2 = computing_zip_assembled(I),
        S3 = S2.put(tier, Tier2),
        bytesio_getvalue(ZipBuffer, ZipBytes),
        ChunkNum is I + 1,
        format(atom(ZipName), '~w.~d.zip', [S3.compute.zipfile_basename, ChunkNum]),
        render_download_link(ZipName, ZipBytes, S3, S4),
        bytesio_close(ZipBuffer),
        S = S4
    ).

%% process_files_loop(+ChunkFiles, +InnerIdx, +ZipHandle, +State0, -State)
process_files_loop([], _, _, S, S).
process_files_loop([File | Rest], J, ZipHandle, S0, S) :-
    pseudonymise_one_file(File, ZipHandle, S0, S1),
    (   S1.compute.bad_data == true
    ->  %% PY:133-134: break out of inner loop on exception
        S = S1
    ;   J1 is J + 1,
        C1 = S1.compute.put(current_file, J1),
        S2 = S1.put(compute, C1),
        process_files_loop(Rest, J1, ZipHandle, S2, S)
    ).

% ============================================================
% Per-file pseudonymisation (the inner-loop body of _zip_pseudo_fifty_mbytes)
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:102-141
%%     for uploaded_file_buffer in file_buffer_list:
%%         file_count += 1
%%         original_file_name = None
%%         try:
%%             original_file_name = uploaded_file_buffer.name
%%             ds_input: pydicom.FileDataset = pydicom.dcmread(uploaded_file_buffer, force=True)
%%             anonymise_dataset(ds_input, delete_private_tags=True, ...)
%%             temp_anon_filepath = build_pseudonymised_file_name(ds_input)
%%             in_memory_temp_file = io.BytesIO()
%%             anon_filename = pathlib.Path(temp_anon_filepath).name
%%             pydicom.dcmwrite(in_memory_temp_file, ds_input)
%%         except (KeyError, OSError, ValueError) as e_info:
%%             print(e_info)
%%             print(f"While processing {original_file_name}")
%%             bad_data = True
%%             break
%%         myzip.writestr(anon_filename, in_memory_temp_file.getvalue(), compress_type=ZIP_DEFLATED)
%%         in_memory_temp_file.close()
pseudonymise_one_file(File, ZipHandle, S0, S) :-
    %% Internal-trace state
    I = S0.compute.current_chunk,
    J = S0.compute.current_file,
    Tier = computing_per_file(I, J),
    S1 = S0.put(tier, Tier),
    %% PY:114-116: try-block start
    catch(
        (   pydicom_dcmread(File.buffer, true, Ds),
            %% PY:96-98: keyword set built once per chunk (PatientSex removed); the
            %% strategy is the per-VR dispatch dict. Modeled here as a single
            %% boundary call with the conventional flag set.
            get_default_pseudonymisation_keywords(Keywords),
            %% PY:97 -- removes 'PatientSex' from the keyword set
            select('PatientSex', Keywords, KeywordsMinusSex),
            anonymise_dataset(Ds, true, true, false, KeywordsMinusSex, pseudonymisation_dispatch),
            build_pseudonymised_filename(Ds, S1, AnonName),
            bytesio_new(InMemTemp),
            pydicom_dcmwrite(InMemTemp, Ds),
            bytesio_getvalue(InMemTemp, AnonBytes),
            zipfile_writestr(ZipHandle, AnonName, AnonBytes, deflate),
            bytesio_close(InMemTemp),
            S = S1
        ),
        E_info,
        (   %% PY:130-134: except (KeyError, OSError, ValueError)
            python_print(E_info),
            print_exception_label(File.name, S1, S2),
            C1 = S2.compute.put(_{bad_data: true, last_exception: E_info}),
            S = S2.put(compute, C1)
        )
    ).

% ============================================================
% Filename derivation
% ============================================================

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:55-78
%%     def build_pseudonymised_file_name(ds_input):
%%         pseudo_sop_instance_uid = pseudonymisation_api.pseudonymisation_dispatch["UI"](ds_input.SOPInstanceUID)
%%         sop_class_uid: pydicom.dataelem.DataElement = ds_input.SOPClassUID
%%         mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[sop_class_uid.name]
%%         anon_filename = f"{mode_prefix}.{pseudo_sop_instance_uid}_Anonymised.dcm"
%%         return anon_filename
build_pseudonymised_filename(Ds, _State, AnonName) :-
    pseudonymisation_dispatch('UI', Ds.'SOPInstanceUID', PseudoSopUid),
    SopClassName = Ds.'SOPClassUID'.name,
    sop_class_mode_prefix(SopClassName, ModePrefix),
    format(atom(AnonName), '~w.~w_Anonymised.dcm', [ModePrefix, PseudoSopUid]).
