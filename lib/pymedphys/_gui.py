# Copyright (C) 2019 Simon Biggs
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
import shutil

from pymedphys._imports import streamlit as st
from pymedphys._imports import tornado

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("_streamlit")


def fill_streamlit_credentials():
    streamlit_config_dir = pathlib.Path.home().joinpath(".streamlit")
    streamlit_config_dir.mkdir(exist_ok=True)

    template_streamlit_credentials_file = STREAMLIT_CONTENT_DIR.joinpath(
        "credentials.toml"
    )
    new_credential_file = streamlit_config_dir.joinpath("credentials.toml")

    try:
        shutil.copy2(template_streamlit_credentials_file, new_credential_file)
    except FileExistsError:
        pass


class HelloWorldHandler(  # pylint: disable = abstract-method
    tornado.web.RequestHandler
):
    def get(self):
        self.write("Hello world!")


def _monkey_patch_streamlit_server():
    """Adds custom URL routes to Streamlit's tornado server."""
    OfficialServer = st.server.server.Server
    official_create_app = OfficialServer._create_app

    def patched_create_app(self):
        app = official_create_app(self)
        base = st.config.get_option("server.baseUrlPath")

        # print(dir(app))
        # print(app.settings)
        # print(app.default_router)
        # print(dir(app.default_router))
        # print(app.default_router.named_rules)

        pattern = st.server.server_util.make_url_path_regex(base, "pymedphys")
        # print(pattern)

        app.add_handlers(".*", [(pattern, HelloWorldHandler)])

        return app

    OfficialServer._create_app = patched_create_app


def main(args):
    """Boot up the pymedphys GUI"""
    fill_streamlit_credentials()

    streamlit_script_path = str(HERE.joinpath("_app.py"))

    if args.port:
        st.cli._apply_config_options_from_cli({"server.port": args.port})

    # Needs to run after config has been set
    _monkey_patch_streamlit_server()

    st._is_running_with_streamlit = True
    st.bootstrap.run(streamlit_script_path, "", [])
