# Code adapted from
# https://github.com/jupyterlab/jupyterlab/blob/1d787dbe2/examples/app/main.py

# Original code under the following license:
# ===================================================================
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
# See https://github.com/jupyterlab/jupyterlab/blob/1d787dbe2/LICENSE
# for more details.
# ===================================================================

# Modifications under the following license:
# ========================================================================
# Copyright (C) 2017-2019 Simon Biggs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.
# ========================================================================

import multiprocessing
import pathlib
import sys
import webbrowser
import zipfile

from pymedphys._imports import jupyterlab_server

import pymedphys

IP = "127.0.0.1"
HERE = pathlib.Path(__file__).parent.resolve()
WORKING_DIRECTORY = HERE.joinpath("working_directory")
BUILD = HERE.joinpath("build")


def launch_server(queue):
    class PyMedPhys(jupyterlab_server.LabServerApp):
        default_url = "/pymedphys"
        description = """
            PyMedPhys
        """
        notebook_dir = str(WORKING_DIRECTORY)
        queue = None
        log_level = 100

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

    # workaround for JupyterApp using sys.argv
    sys.argv = [sys.argv[0]]
    PyMedPhys.launch_instance(queue=queue, ip=IP, open_browser=False)


def main(args):
    if not BUILD.is_dir():
        cached_data = pymedphys.data_path("app_build.zip")

        with zipfile.ZipFile(cached_data, "r") as zip_file:
            zip_file.extractall(HERE)

    queue = multiprocessing.Queue()

    server_process = multiprocessing.Process(target=launch_server, args=(queue,))
    server_process.start()

    port, token = queue.get()
    url = f"http://{IP}:{port}/?token={token}"

    sys.stdout.write(f'\n{{"url": "{url}"}}\n')
    sys.stdout.flush()

    if not args.no_browser:
        webbrowser.open(url)
