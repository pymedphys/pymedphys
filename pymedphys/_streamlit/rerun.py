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
def rerun_on_module_reload(module: types.ModuleType, session_id):
    observer = polling.PollingObserver()

    module_directory = pathlib.Path(module.__file__).parent

    event_handler = WatchdogEventHandler(module, session_id)
    observer.schedule(event_handler, module_directory, recursive=False)

    observer.start()


def auto_reload_on_module_changes(modules):
    session_id = get_session_id()

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    for module in modules:
        rerun_on_module_reload(module, session_id)
