import multiprocessing
import secrets
import sys

import notebook.notebookapp
import pymedphys
from cefpython3 import cefpython as cef

IP = "127.0.0.1"


class PyMedPhys(notebook.notebookapp.NotebookApp):
    name = "PyMedPhys"
    version = pymedphys.__version__
    description = """
        PyMedPhys
        Kernel hosting for PyMedPhys app.
    """
    # default_url = "/"
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
