import multiprocessing
import pathlib
import sys

import jupyterlab.labapp
from cefpython3 import cefpython as cef

import pymedphys

IP = "127.0.0.1"
HERE = pathlib.Path(__file__).parent.resolve()
WORKING_DIRECTORY = HERE.joinpath("working_directory")


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


def launch_kernel_server(queue):
    PyMedPhys.launch_instance(queue=queue, ip=IP, open_browser=False)


def main():
    sys.excepthook = cef.ExceptHook

    queue = multiprocessing.Queue()

    kernel_process = multiprocessing.Process(target=launch_kernel_server, args=(queue,))
    kernel_process.start()

    port, token = queue.get()
    url = f"http://{IP}:{port}/?token={token}"

    cef.Initialize()
    cef.CreateBrowserSync(url=url)
    cef.MessageLoop()
    cef.Shutdown()


if __name__ == "__main__":
    main()
