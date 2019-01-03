# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


import os

from notebook.base.handlers import IPythonHandler
from notebook.utils import url_path_join as ujoin

from jinja2 import FileSystemLoader

HERE = os.path.dirname(__file__)
GUI_PATH = os.path.join(HERE, 'gui')
LOADER = FileSystemLoader(GUI_PATH)


def get_pymedphys_handlers(base_url):
    pymedphys_handlers = [
        (
            ujoin(base_url, r'/pymedphys/.*'),
            PyMedPhysHandler
        )
    ]

    return pymedphys_handlers


class PyMedPhysHandler(IPythonHandler):
    def get(self):
        return self.write(
            self.render_template("index.html", base_url=self.base_url))

    def get_template(self, name):
        return LOADER.load(self.settings['jinja2_env'], name)


def _jupyter_server_extension_paths():
    return [{
        "module": "pymedphys"
    }]


def load_jupyter_server_extension(notebook_app):
    web_app = notebook_app.web_app
    base_url = web_app.settings['base_url']
    handlers = get_pymedphys_handlers(base_url)

    web_app.add_handlers(".*$", handlers)
