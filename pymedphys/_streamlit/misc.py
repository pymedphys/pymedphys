# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name


import importlib
import pathlib
import queue
import time
import types

from rx import operators, subject
from watchdog import events, observers

import streamlit as st

from . import config


def site_picker(radio_label, default=None, key=None):
    site_directories = config.get_site_directories()
    site_options = list(site_directories.keys())

    if default is None:
        default_index = 0
    else:
        default_index = site_options.index(default)
    chosen_site = st.radio(radio_label, site_options, index=default_index, key=key)

    return chosen_site


def get_site_and_directory(radio_label, directory_label, default=None, key=None):
    site_directories = config.get_site_directories()

    chosen_site = site_picker(radio_label, default=default, key=key)
    directory = site_directories[chosen_site][directory_label]

    return chosen_site, directory


def rerun(rerun_data=None):
    raise st.script_runner.RerunException(st.script_request_queue.RerunData(None))


class WatchdogEventHandler(events.FileModifiedEvent):
    def __init__(self, module, module_bucket):
        self.module = module
        self.module_bucket = module_bucket

        super().__init__(self.module.__file__)

    def dispatch(self, event):
        if event.src_path == self.module.__file__:
            print(self.module.__file__)
            self.module_bucket.on_next(self.module)


def rerun_on_module_reload(module: types.ModuleType, module_bucket):
    observer = observers.Observer()

    module_directory = pathlib.Path(module.__file__).parent

    event_handler = WatchdogEventHandler(module, module_bucket)
    observer.schedule(event_handler, module_directory, recursive=False)

    observer.start()


# @st.cache(suppress_st_warning=True)
def auto_reload_on_module_changes(current_module, modules):
    ctx = st.report_thread.get_report_ctx()

    print("dg")
    print(dir(ctx))  ###

    if isinstance(modules, types.ModuleType):
        modules = [modules]

    # module_bucket = subject.Subject()
    # debounced = operators.debounce(0.2)(module_bucket)
    modules.append(current_module)

    for module in modules:
        rerun_on_module_reload(module, ctx)

    def wait_for_rerun():
        module = debounced.run()

        if module != current_module:
            importlib.reload(module)

        print(f"I reran {module}")

        ctx.enqueue(st.script_request_queue.ScriptRequest.RERUN)

    return wait_for_rerun
