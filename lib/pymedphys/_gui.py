# Copyright (C) 2026 Matthew Jennings
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

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("_streamlit")

DEFAULT_ADDRESS = "localhost"


def main(args):
    """Boot up the pymedphys GUI"""
    _fill_streamlit_credentials()

    subprocess.check_call(build_streamlit_command(port=args.port, address=args.address))


def build_streamlit_command(
    port: int | None = None, address: str = DEFAULT_ADDRESS
) -> list[str]:
    """Return the command that starts the PyMedPhys GUI with Streamlit.

    Streamlit listens on every network interface unless ``server.address``
    is set, and sends usage statistics unless they are disabled. The GUI can
    display patient data, so the command always sets both. Command-line flags
    take precedence over Streamlit configuration files and environment
    variables.

    Parameters
    ----------
    port : int, optional
        The port to serve on. If ``None``, Streamlit's own default applies.
    address : str, optional
        The address to listen on. Defaults to ``"localhost"``, so that only
        the computer running the GUI can connect to it.

    Returns
    -------
    list of str
        The command, suitable for ``subprocess.check_call``.
    """
    options = [
        "--server.address",
        address,
        "--browser.gatherUsageStats",
        "false",
    ]
    if port is not None:
        options += ["--server.port", str(port)]

    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        *options,
        str(HERE.joinpath("_app.py")),
    ]


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
