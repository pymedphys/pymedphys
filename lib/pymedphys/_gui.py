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

import importlib.util
import pathlib
import shutil
import subprocess
import sys

from pymedphys import _extras

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("_streamlit")

LOOPBACK_ADDRESS = "127.0.0.1"
LOOPBACK_HOSTS = ("localhost", LOOPBACK_ADDRESS)


def main(args):
    """Boot up the pymedphys GUI"""
    # Streamlit runs in a subprocess, whose error would not say which extra
    # provides it.
    if importlib.util.find_spec("streamlit") is None:
        raise ModuleNotFoundError(
            _extras.missing_dependency_message("streamlit", "pymedphys gui"),
            name="streamlit",
        )

    _fill_streamlit_credentials()

    streamlit_script_path = str(HERE.joinpath("_app.py"))
    options = streamlit_options(port=args.port, address=args.address)

    subprocess.check_call(
        [sys.executable, "-m", "streamlit", "run", *options, streamlit_script_path]
    )


def streamlit_options(port: int | None, address: str | None) -> list[str]:
    """Return the ``streamlit run`` options that serve the GUI.

    Streamlit gives command line options precedence over its environment
    variables and configuration files, so these settings always apply.

    Parameters
    ----------
    port
        The port to serve on, or ``None`` for Streamlit's configured port.
    address
        The network address to serve on, or ``None`` to serve only this
        computer on the loopback address. Streamlit then also accepts the
        WebSocket connections that run the apps only when they are addressed
        to ``localhost`` or the loopback address, which protects those
        connections against DNS rebinding. With an explicit address, the
        accepted host names are left to Streamlit's ``server.allowedHosts``
        setting, which by default accepts any.

    Returns
    -------
    list[str]
        Options to pass to ``streamlit run`` before the script path.
    """
    options = ["--browser.gatherUsageStats", "false"]

    if address is None:
        options += ["--server.address", LOOPBACK_ADDRESS]
        for host in LOOPBACK_HOSTS:
            options += ["--server.allowedHosts", host]
    else:
        options += ["--server.address", address]

    if port is not None:
        options += ["--server.port", str(port)]

    return options


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
