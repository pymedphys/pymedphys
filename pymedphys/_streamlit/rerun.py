# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name


import importlib
import pathlib
import types

from watchdog import events
from watchdog.observers import polling

import streamlit as st


def get_session_id():
    ctx = st.report_thread.get_report_ctx()
    session_id = ctx.session_id

    return session_id


def rerun(session_id=None):
    if session_id is None:
        session_id = get_session_id()

    server = st.server.server.Server.get_current()
    session = server._get_session_info(  # pylint: disable = protected-access
        session_id
    ).session

    session.request_rerun()


@st.cache()
def reload_and_rerun_on_module_changes(module: types.ModuleType, session_id):
    event_handler = events.FileModifiedEvent(module.__file__)

    def dispatch(event):
        if event.src_path == module.__file__:
            importlib.reload(module)
            rerun(session_id)

    event_handler.dispatch = dispatch

    module_directory = pathlib.Path(module.__file__).parent

    # If a normal observer is used here sometimes there can be a burst
    # of observations triggered (for example when using VS Code). By
    # using polling here this effectively debounces the observation
    # signal.
    observer = polling.PollingObserver()
    observer.schedule(event_handler, module_directory, recursive=False)
    observer.start()


# An issue with this implementation of autoreload is that should
# this function be removed from a streamlit app the listener doesn't
# actually go away. Once a listener is added it is persistent until
# the cache is cleared.

# TODO: Provide a parameter deregister_all_other_listeners, or something
# similar, that defaults to True. When autoreload is called, the first
# thing that is done is it is determined whether or not observers
# are currently running on this session_id that have not been provided
# to the current function. If that's the case, those observers are
# stopped.


def autoreload(modules):
    session_id = get_session_id()

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    for module in modules:
        reload_and_rerun_on_module_changes(module, session_id)
