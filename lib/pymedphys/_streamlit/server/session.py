# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# It is understood that we are stepping into 'private' API usage here
# pylint: disable = protected-access

import pathlib
from typing import BinaryIO, Union

from pymedphys._imports import streamlit as st

File = Union[pathlib.Path, str, BinaryIO]


class SessionState:
    def __init__(self, state):
        for key, val in state.items():
            setattr(self, key, val)

    def update(self, state):
        for key, val in state.items():
            try:
                getattr(self, key)
            except AttributeError:
                setattr(self, key, val)


def get_session_id() -> str:
    ctx = st.scriptrunner.add_script_run_ctx()
    session_id: str = ctx.streamlit_script_run_ctx.session_id

    return session_id


def get_session(session_id: str = None):
    if session_id is None:
        session_id = get_session_id()

    session_info = st.server.server.Server.get_current()._get_session_info(session_id)

    if session_info is None:
        raise ValueError("No session info found")

    report_session = session_info.session

    return report_session


def session_state(**state):
    session = get_session()

    try:
        session._custom_session_state.update(state)
    except AttributeError:
        session._custom_session_state = SessionState(state)

    return session._custom_session_state
