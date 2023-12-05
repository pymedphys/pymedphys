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

import uuid
from typing import Union

from pymedphys._imports import streamlit as st

from . import session

FileContent = Union[str, bytes]


def download(name: str, content: FileContent):
    """Create a Streamlit download link to the given file content.

    Parameters
    ----------
    name : str
        The filename of the download. If a previous download link has
        been provided with the same download name the previous filepath
        will be overwritten.
    content : str or bytes
        The content of the file to be downloaded.
    """

    url = _add_file_get_url(name, content)

    href = f"""
        <a href="{url}" download='{name}'>
            Click to download `{name}`
        </a>
    """
    st.markdown(href, unsafe_allow_html=True)


def get_download_file(session_id: uuid.UUID, name: str) -> bytes:
    report_session = session.get_session(session_id=session_id)
    content: FileContent = report_session.downloads[name]

    if isinstance(content, str):
        content = content.encode()

    return content


def set_download_file(name: str, content: FileContent):
    report_session = session.get_session()

    try:
        report_session.downloads[name] = content
    except AttributeError:
        report_session.downloads = {name: content}


def _add_file_get_url(name: str, content: FileContent) -> str:
    session_id = session.get_session_id()
    url = f"downloads/{session_id}/{name}"

    set_download_file(name, content)

    return url
