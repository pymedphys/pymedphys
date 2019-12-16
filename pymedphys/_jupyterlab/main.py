# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import multiprocessing
import pathlib
import sys
import zipfile

from pymedphys._imports import jupyterlab_server

import pymedphys

IP = "127.0.0.1"
HERE = pathlib.Path(__file__).parent.resolve()
BUILD = HERE.joinpath("build")


def launch_server(queue, working_directory):
    class JupyterLabStandalone(jupyterlab_server.LabServerApp):
        default_url = "/lab"
        notebook_dir = str(working_directory)
        queue = None
        log_level = 100

        lab_config = jupyterlab_server.LabConfig(
            app_name="JupyterLab",
            app_settings_dir=str(BUILD.joinpath("application_settings")),
            app_version=pymedphys.__version__,
            app_url="/lab",
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

    # workaround for JupyterApp using sys.argv
    sys.argv = [sys.argv[0]]
    JupyterLabStandalone.launch_instance(queue=queue, ip=IP, open_browser=False)


def get_build():
    if not BUILD.is_dir():
        print("Downloading JupyterLab...")
        cached_data = pymedphys.data_path("lab_build.zip")

        with zipfile.ZipFile(cached_data, "r") as zip_file:
            zip_file.extractall(HERE)


def main(args):
    get_build()

    queue = multiprocessing.Queue()

    server_process = multiprocessing.Process(
        target=launch_server, args=(queue, args.working_directory)
    )
    server_process.start()

    port, token = queue.get()
    url = f"http://{IP}:{port}/?token={token}"

    sys.stdout.write(f'\n{{"url": "{url}"}}\n')
    sys.stdout.flush()
