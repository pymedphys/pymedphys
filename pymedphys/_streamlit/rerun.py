# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name


import importlib
import pathlib
import queue
import types

from watchdog import events, observers

import streamlit as st


def foo():
    st.write("foo")


def rerun(rerun_data=None):
    raise st.script_runner.RerunException(st.script_request_queue.RerunData(None))


class WatchdogEventHandler(events.FileModifiedEvent):
    def __init__(self, module, module_bucket):
        self.module = module
        self.module_bucket = module_bucket

        super().__init__(self.module.__file__)

    def dispatch(self, event):
        if event.src_path == self.module.__file__:
            self.module_bucket.put(self.module)


def rerun_on_module_reload(module: types.ModuleType, module_bucket):
    observer = observers.polling.PollingObserver()

    module_directory = pathlib.Path(module.__file__).parent

    event_handler = WatchdogEventHandler(module, module_bucket)
    observer.schedule(event_handler, module_directory, recursive=False)

    observer.start()


@st.cache(suppress_st_warning=True)
def auto_reload_on_module_changes(current_module_name, modules):
    current_module = importlib.import_module(current_module_name)

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    modules.append(current_module)
    module_bucket = queue.Queue()

    for module in modules:
        rerun_on_module_reload(module, module_bucket)

    def wait_for_rerun():
        module = module_bucket.get(block=True)
        if module != current_module:
            print(f"Reloading {module.__file__}")
            importlib.reload(module)

        print("Rerunning streamlit")
        rerun()

    return wait_for_rerun
