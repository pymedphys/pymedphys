%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Auxiliary list module for the 50-MByte chunk-index computation. Mirrors
%% `_gen_index_list_to_fifty_mbyte_increment` at PY:201-229 verbatim in
%% predicate form.
%%
%% The chunking exists because the data: URL download mechanism used at PY:48-52
%% has a 50 MByte limit imposed by browser href-data: caps. The compression
%% used (DEFLATE) is applied AFTER the chunk boundary is decided based on
%% UNCOMPRESSED size, so a single uncompressed file >50 MByte that does not
%% compress under 50 MByte will fail download and may cause the entire
%% pseudonymisation attempt to fail (PY:152-155 docstring).

:- module(chunk_index_list, [
    fifty_mbyte_threshold/1,        % fifty_mbyte_threshold(-Bytes)
    compute_chunks/2,               % compute_chunks(+UploadedFiles, -EndIndices)
    chunk_count/2,                  % chunk_count(+EndIndices, -N)
    next_chunk_bounds/4             % next_chunk_bounds(+EndIndices, +CurrentIdx, -Start, -End)
]).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:222
%%     if size > 50000000:
%% Hard-coded threshold; the magic number lives at the call site in the source.
fifty_mbyte_threshold(50000000).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:201-229
%%     def _gen_index_list_to_fifty_mbyte_increment(file_buffer_list):
%%         file_count = 0
%%         index_to_fifty_mbyte_increment = list()
%%         size = 0
%%         for uploaded_file_buffer in file_buffer_list:
%%             file_count += 1
%%             size += uploaded_file_buffer.size
%%             if size > 50000000:
%%                 index_to_fifty_mbyte_increment.append(file_count)
%%                 size = 0
%%         if size != 0:
%%             index_to_fifty_mbyte_increment.append(file_count)
%%         return index_to_fifty_mbyte_increment
%%
%% Behavior preserved verbatim, including:
%%   - the post-loop `if size != 0` tail-flush (the trailing partial chunk),
%%   - the threshold being a strict `>`, not `>=`, so a file of exactly
%%     50_000_000 bytes does NOT trigger a split,
%%   - the size accumulator being reset to 0 on split (no carry-over of the
%%     overshoot).
compute_chunks(Files, EndIndices) :-
    fifty_mbyte_threshold(Threshold),
    chunks_loop(Files, 0, 0, Threshold, [], RevEnds),
    reverse(RevEnds, EndIndices).

%% chunks_loop(+Files, +FileCountAcc, +SizeAcc, +Threshold, +RevEndsAcc, -RevEnds)
chunks_loop([], _FC, 0, _T, RevEnds, RevEnds).
chunks_loop([], FC, Size, _T, RevEnds, [FC | RevEnds]) :-
    Size > 0.   %% PY:226-227 tail-flush
chunks_loop([File | Rest], FC0, Size0, T, RevEnds0, RevEnds) :-
    FC1 is FC0 + 1,
    Size1 is Size0 + File.size,
    (   Size1 > T
    ->  RevEnds1 = [FC1 | RevEnds0],
        Size2 = 0
    ;   RevEnds1 = RevEnds0,
        Size2 = Size1
    ),
    chunks_loop(Rest, FC1, Size2, T, RevEnds1, RevEnds).

chunk_count(EndIndices, N) :-
    length(EndIndices, N).

%% next_chunk_bounds(+EndIndices, +CurrentIdx, -Start, -End)
%% Pseudonymise's outer loop iterates with start_index = previous-end, end_index =
%% next chunk-end. Mirrors the start_index/end_index threading at PY:176-186.
next_chunk_bounds(EndIndices, 0, 0, End) :-
    nth0(0, EndIndices, End).
next_chunk_bounds(EndIndices, CurrentIdx, Start, End) :-
    CurrentIdx > 0,
    Prev is CurrentIdx - 1,
    nth0(Prev, EndIndices, Start),
    nth0(CurrentIdx, EndIndices, End).
