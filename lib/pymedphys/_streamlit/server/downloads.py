# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collections
import pathlib
from typing import Dict

from pymedphys._imports import streamlit as st

from .session import SessionID, get_session_id

FileName = str
FilePath = pathlib.Path
FileLocationMap = Dict[SessionID, Dict[FileName, FilePath]]


# Assuming CPython with the GIL is being used. This implies that Dicts
# are thread-safe:
#
#    <https://docs.python.org/3/glossary.html#term-global-interpreter-lock>

# More info regarding thread-safety of default-dict:
#
# <https://stackoverflow.com/a/17682555/3912576>

# Importantly this assumption only applies if __hash__ and __eq__ of the
# keys don't call Python. Keys here are of str type, so OK.

# Nevertheless... placing a lock around this object, or utilising a
# Queue, in its final implementation would be prudent.

file_location_map: FileLocationMap = collections.defaultdict(dict)

# TODO: Adjust this object later to hook into when Streamlit sessions
# are closed. Potentially utilise an object similar to, or based on,
# session state objects?


def download(filename: str, filepath: pathlib.Path):
    """Create a Streamlit download link to a given file.

    Parameters
    ----------
    filename : str
        The filename of the download. If a previous download link has
        been provided with the same download name the previous filepath
        will be overwritten.
    filepath : pathlib.Path
        The full filepath of the file to be downloaded.
    """

    url = _add_filepath_get_url(filename, filepath)

    href = f"""
        <a href="{url}" download='{filename}'>
            Click to download `{filename}`
        </a>
    """
    st.markdown(href, unsafe_allow_html=True)


def _add_filepath_get_url(filename: str, filepath: pathlib.Path):
    session_id = get_session_id()
    url = f"downloads/{session_id}/{filename}"

    file_location_map[session_id][filename] = filepath

    return url
