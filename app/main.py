# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import ctypes
import multiprocessing
import pathlib
import platform
import sys

from cefpython3 import cefpython as cef

import jupyterlab_server
import pymedphys
import traitlets

IP = "127.0.0.1"
HERE = pathlib.Path(__file__).parent.resolve()
WORKING_DIRECTORY = HERE.joinpath("working_directory")
BUILD = HERE.joinpath("build")
SCREEN_SIZE = (0, 0, 1920, 1080)


class PyMedPhys(jupyterlab_server.LabServerApp):
    default_url = traitlets.Unicode(
        "/pymedphys", help="The default URL to redirect to from `/`"
    )

    description = """
        PyMedPhys
    """
    notebook_dir = str(WORKING_DIRECTORY)
    queue = None

    lab_config = jupyterlab_server.LabConfig(
        app_name="PyMedPhys",
        app_settings_dir=str(BUILD.joinpath("application_settings")),
        app_version=pymedphys.__version__,
        app_url="/pymedphys",
        schemas_dir=str(BUILD.joinpath("schemas")),
        static_dir=str(BUILD),
        templates_dir=str(HERE.joinpath("templates")),
        themes_dir=str(BUILD.joinpath("themes")),
        user_settings_dir=str(BUILD.joinpath("user_settings")),
        workspaces_dir=str(BUILD.joinpath("workspaces")),
    )

    def start(self):
        settings = self.web_app.settings
        settings.setdefault("terminals_available", True)

        super().start()

    def initialize(self, argv=None):
        super_result = super().initialize(argv=argv)

        self.queue.put((self.port, self.token))

        return super_result


def launch_server(queue):
    PyMedPhys.launch_instance(queue=queue, ip=IP, open_browser=False)


def main():
    sys.excepthook = cef.ExceptHook

    queue = multiprocessing.Queue()

    server_process = multiprocessing.Process(target=launch_server, args=(queue,))
    server_process.start()

    cef.Initialize()
    window_info = cef.WindowInfo()
    parent_handle = 0
    window_info.SetAsChild(parent_handle, list(SCREEN_SIZE))

    port, token = queue.get()
    url = f"http://{IP}:{port}/?token={token}"
    browser = cef.CreateBrowserSync(url=url, window_info=window_info)

    if platform.system() == "Windows":
        window_handle = browser.GetOuterWindowHandle()
        insert_after_handle = 0
        SWP_NOMOVE = 0x0002
        ctypes.windll.user32.SetWindowPos(
            window_handle, insert_after_handle, *SCREEN_SIZE, SWP_NOMOVE
        )

    cef.MessageLoop()
    cef.Shutdown()


if __name__ == "__main__":
    main()
