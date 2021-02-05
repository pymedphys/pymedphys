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

import pathlib
from typing import BinaryIO, Union

from pymedphys._imports import streamlit as st

from . import session

File = Union[pathlib.Path, str, BinaryIO]


def download(name: str, file: File):
    """Create a Streamlit download link to a given file.

    Parameters
    ----------
    name : str
        The filename of the download. If a previous download link has
        been provided with the same download name the previous filepath
        will be overwritten.
    file : pathlib.Path, str, or io.BytesIO
        The file to be downloaded.
    """

    url = _add_file_get_url(name, file)

    href = f"""
        <a href="{url}" download='{name}'>
            Click to download `{name}`
        </a>
    """
    st.markdown(href, unsafe_allow_html=True)


def _add_file_get_url(filename: str, file: File) -> str:
    session_id = session.get_session_id()
    url = f"downloads/{session_id}/{filename}"

    session.set_download_file(filename, file)

    return url
