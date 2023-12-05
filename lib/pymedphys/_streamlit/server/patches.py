# Copyright (C) 2021 Simon Biggs, Cancer Care Associates
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable = protected-access

import pathlib
import uuid
from typing import Any, Dict, Tuple

from pymedphys._imports import streamlit as st
from pymedphys._imports import tornado

from . import downloads

THIS = pathlib.Path(__file__).resolve()
PYMEDPHYS_ROOT = THIS.parents[2]
DOCS_BUILD_HTML = PYMEDPHYS_ROOT / "docs" / "_build" / "html"

Handlers = Dict[str, Tuple[Any, Dict[str, Any]]]


def apply_streamlit_server_patches():
    """Apply the PyMedPhys streamlit server extensions.

    Must be run after Streamlit configuration has been set, but before
    the server starts.
    """
    _monkey_patch_streamlit_server()


def _monkey_patch_streamlit_server():
    """Adds custom URL routes to Streamlit's tornado server."""
    handlers = _create_handlers()

    OfficialServer = st.server.server.Server
    official_create_app = OfficialServer._create_app

    def patched_create_app(self: st.server.server.Server) -> tornado.web.Application:
        app: tornado.web.Application = official_create_app(self)

        base: str = st.config.get_option("server.baseUrlPath")

        rules: tornado.routing._RuleList = []
        for key, (handler, kwargs) in handlers.items():
            pattern = st.server.server_util.make_url_path_regex(base, key)
            rules.append((pattern, handler, kwargs))

        app.add_handlers(".*", rules)

        return app

    OfficialServer._create_app = patched_create_app


def _create_handlers() -> Handlers:
    class HelloWorldHandler(  # pylint: disable = abstract-method
        tornado.web.RequestHandler
    ):
        def get(self):
            self.write("Hello world!")

    class DownloadHandler(  # pylint: disable = abstract-method
        tornado.web.RequestHandler
    ):
        def get(self, session_id: uuid.UUID, name: str):
            file_bytes = downloads.get_download_file(session_id, name)

            self.write(file_bytes)
            self.finish()

    return {
        "pymedphys": (HelloWorldHandler, {}),
        "downloads/(.*)/(.*)": (DownloadHandler, {}),
        "docs/(.*)": (tornado.web.StaticFileHandler, {"path": DOCS_BUILD_HTML}),
    }
