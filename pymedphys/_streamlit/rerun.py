# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name


import importlib
import pathlib
import types

from watchdog import events
from watchdog.observers import polling

import streamlit as st


def rerun(session=None):
    if session is None:
        ctx = st.report_thread.get_report_ctx()
        server = st.server.server.Server.get_current()
        session = server._session_info_by_id[  # pylint: disable = protected-access
            ctx.session_id
        ].session

    session.request_rerun()


class WatchdogEventHandler(events.FileModifiedEvent):
    def __init__(self, module, session):
        self.module = module
        self.session = session

        super().__init__(self.module.__file__)

    def dispatch(self, event):
        if event.src_path == self.module.__file__:
            print(f"Reloading {self.module.__file__}")
            importlib.reload(self.module)
            print("Rerunning streamlit session")
            rerun(self.session)


@st.cache()
def rerun_on_module_reload(module: types.ModuleType, session_id):
    server = st.server.server.Server.get_current()
    session = server._session_info_by_id[  # pylint: disable = protected-access
        session_id
    ].session

    observer = polling.PollingObserver()

    module_directory = pathlib.Path(module.__file__).parent

    event_handler = WatchdogEventHandler(module, session)
    observer.schedule(event_handler, module_directory, recursive=False)

    observer.start()


def auto_reload_on_module_changes(modules):
    ctx = st.report_thread.get_report_ctx()
    session_id = ctx.session_id

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    for module in modules:
        rerun_on_module_reload(module, session_id)
