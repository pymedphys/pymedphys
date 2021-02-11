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

from pymedphys._streamlit.server import start

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("_streamlit")


def main(args):
    """Boot up the pymedphys GUI"""
    _fill_streamlit_credentials()

    streamlit_script_path = str(HERE.joinpath("_app.py"))

    if args.port:
        config = {"server.port": args.port}
    else:
        config = {}

    start.start_streamlit_server(streamlit_script_path, config)


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
