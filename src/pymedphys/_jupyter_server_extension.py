# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


import os
import re
from glob import glob

from notebook.base.handlers import IPythonHandler, FileFindHandler
from notebook.utils import url_path_join as ujoin

from jinja2 import FileSystemLoader, Markup

HERE = os.path.dirname(__file__)
GUI_PATH = os.path.join(HERE, 'gui', 'build')
LOADER = FileSystemLoader(GUI_PATH)


def get_pymedphys_handlers(base_url):
    build_dir = os.path.join(GUI_PATH)
    build_files = glob(os.path.join(build_dir, '**'), recursive=True)

    print(build_dir)

    rel_paths = [os.path.relpath(item, build_dir) for item in build_files]
    forward_slash = [path.replace('\\', '/') for path in rel_paths]

    build_escaped = [re.escape(item) for item in forward_slash]
    build_strings = '|'.join(build_escaped)

    static_handler_regex = "/pymedphys/({})".format(build_strings)

    print(static_handler_regex)

    pymedphys_handlers = [
        (
            ujoin(base_url, static_handler_regex),
            FileFindHandler,
            {'path': build_dir}
        ),
        (
            ujoin(base_url, r'/pymedphys.*'),
            PyMedPhysHandler
        )
    ]

    return pymedphys_handlers


class PyMedPhysHandler(IPythonHandler):
    def get(self):
        base_tag = Markup(
            '<base href="{}pymedphys/"></base>'.format(self.base_url))
        return self.write(self.render_template(
            "index.html", base_url=self.base_url, base_tag=base_tag))

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
