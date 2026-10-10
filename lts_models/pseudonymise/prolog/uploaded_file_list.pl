%% Source: lib/pymedphys/_streamlit/apps/pseudonymise.py
%%
%% Auxiliary list module for the file_uploader's UploadedFile list. Each
%% element of the list is a dict mirroring the public surface of Streamlit's
%% UploadedFile object that this app actually reads:
%%
%%   uploaded_file{
%%     name: Atom,           % `uploaded_file_buffer.name`        (PY: pseudonymise.py:113)
%%     size: Int,            % `uploaded_file_buffer.size`        (PY: pseudonymise.py:221)
%%     buffer: Term          % opaque BytesIO-like handle passed to pydicom.dcmread
%%   }
%%
%% Streamlit's runtime owns the buffer's open/close lifecycle. The pseudonymise
%% app deliberately does NOT close it; see the comment block at PY:105-108:
%%
%%     "don't close the buffers. Streamlit provides the user with control over that.
%%      might be appropriate to close the buffers in some circumstances, but then
%%      when the user goes to close the buffer (click x on screen) there will be an
%%      error."
%%
%% That decision is reflected in this module by the absence of any close/free
%% predicates -- there's nothing for the LTS to model.

:- module(uploaded_file_list, [
    empty_uploaded_files/1,         % empty_uploaded_files(-List)
    nth_uploaded_file/3,            % nth_uploaded_file(+Index, +List, -File)
    slice_uploaded_files/4,         % slice_uploaded_files(+Start, +End, +List, -SliceList)
    total_size/2,                   % total_size(+List, -Bytes)
    file_count/2,                   % file_count(+List, -N)
    is_empty/1                      % is_empty(+List)
]).

empty_uploaded_files([]).

%% Standard nth0 wrapper for clarity at call sites.
nth_uploaded_file(Index, List, File) :-
    nth0(Index, List, File).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:184
%%     file_buffer_list[start_index:end_index]
%% Mirrors Python's half-open slice [Start, End).
slice_uploaded_files(Start, End, List, Slice) :-
    length(Prefix, Start),
    append(Prefix, Rest, List),
    SliceLen is End - Start,
    length(Slice, SliceLen),
    append(Slice, _, Rest).

%% PY: lib/pymedphys/_streamlit/apps/pseudonymise.py:218-221 -- size accumulator in
%% _gen_index_list_to_fifty_mbyte_increment.
total_size(List, Total) :-
    foldl(add_size, List, 0, Total).
add_size(File, Acc, Sum) :-
    Sum is Acc + File.size.

file_count(List, N) :-
    length(List, N).

is_empty([]).
