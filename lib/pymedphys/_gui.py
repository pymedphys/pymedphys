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

import json
import pathlib
import shutil
import sys

from pymedphys._imports import streamlit as st

from pymedphys._streamlit.server import start

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("_streamlit")


def main(args):
    """Boot up the pymedphys GUI"""
    _fill_streamlit_credentials()

    streamlit_script_path = str(HERE.joinpath("_app.py"))

    config = {}

    if args.port:
        config["server.port"] = args.port

    if args.electron:
        _patch_streamlit_print_url()
        config["server.headless"] = True

    start.start_streamlit_server(streamlit_script_path, config)


def _patch_streamlit_print_url():
    _original_print_url = st.bootstrap._print_url

    def _new_print_url(is_running_hello: bool) -> None:
        port = int(st.config.get_option("browser.serverPort"))

        sys.stdout.flush()
        print(json.dumps({"port": port}))
        sys.stdout.flush()

        _original_print_url(is_running_hello)

    st.bootstrap._print_url = _new_print_url


def _fill_streamlit_credentials():
    streamlit_config_file = pathlib.Path.home().joinpath(
        ".streamlit", "credentials.toml"
    )
    if streamlit_config_file.exists():
        return

    streamlit_config_dir = streamlit_config_file.parent
    streamlit_config_dir.mkdir(exist_ok=True)

    template_streamlit_config_file = STREAMLIT_CONTENT_DIR.joinpath("credentials.toml")

    try:
        shutil.copy2(template_streamlit_config_file, streamlit_config_file)
    except FileExistsError:
        pass
