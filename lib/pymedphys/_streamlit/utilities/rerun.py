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


import importlib
import pathlib
import types

from pymedphys._imports import streamlit as st
from pymedphys._imports import watchdog

from . import session as _session


def rerun(session_id=None):
    if session_id is None:
        session_id = _session.get_session_id()

    server = st.server.server.Server.get_current()
    session = server._get_session_info(  # pylint: disable = protected-access
        session_id
    ).session

    session.request_rerun()


@st.cache()
def reload_and_rerun_on_module_changes(module: types.ModuleType, session_id):
    event_handler = watchdog.events.FileModifiedEvent(module.__file__)

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
    observer = watchdog.observers.polling.PollingObserver()
    observer.schedule(event_handler, module_directory, recursive=False)
    observer.start()


# An issue with this implementation of autoreload is that should
# this function be removed from a streamlit app the listener doesn't
# actually go away. Once a listener is added it is persistent until
# the cache is cleared.

# TODO: Make it so that instead of creating an observer for every
# session_id, instead, if a file is already being observed, just append
# the new session_id to the rerun trigger.

# TODO: Provide a way to automatically deregister the listeners in the
# case where the autoreload function is no longer being called, or
# some modules are no longer being provided to autoreload function

# TODO: Also need to deregister the reload observer when a session is
# closed.


def autoreload(modules):
    session_id = _session.get_session_id()

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    for module in modules:
        reload_and_rerun_on_module_changes(module, session_id)


@st.cache(allow_output_mutation=True)
def mutable_file_contents_cache(path):
    with open(path) as f:
        data = f.read()

    return {"file_contents": data}


def file_contents(path):
    path = pathlib.Path(path)
