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


class WatchdogEventHandler(events.FileModifiedEvent):
    def __init__(self, module, session_id):
        self.module = module
        self.session_id = session_id

        super().__init__(self.module.__file__)

    def dispatch(self, event):
        if event.src_path == self.module.__file__:
            print(f"Reloading {self.module.__file__}")
            importlib.reload(self.module)
            print("Rerunning streamlit session")
            rerun(self.session_id)


@st.cache()
def reload_and_rerun_on_module_changes(module: types.ModuleType, session_id):
    observer = polling.PollingObserver()

    module_directory = pathlib.Path(module.__file__).parent

    event_handler = WatchdogEventHandler(module, session_id)
    observer.schedule(event_handler, module_directory, recursive=False)

    observer.start()


def autoreload(modules):
    session_id = get_session_id()

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    for module in modules:
        reload_and_rerun_on_module_changes(module, session_id)
