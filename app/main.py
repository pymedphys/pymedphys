import ctypes
import multiprocessing
import pathlib
import platform
import sys

import jupyterlab.labapp
from cefpython3 import cefpython as cef

import pymedphys

IP = "127.0.0.1"
HERE = pathlib.Path(__file__).parent.resolve()
WORKING_DIRECTORY = HERE.joinpath("working_directory")
SCREEN_SIZE = (0, 0, 1920, 1080)


class PyMedPhys(jupyterlab.labapp.LabApp):
    name = "PyMedPhys"
    version = pymedphys.__version__
    description = """
        PyMedPhys
        Kernel hosting for PyMedPhys app.
    """
    notebook_dir = str(WORKING_DIRECTORY)
    queue = None

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
