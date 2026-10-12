# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2020 Cancer Care Associates
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse

from pymedphys._gui import main


def gui_cli(subparsers: argparse._SubParsersAction):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "gui", help=("Run the PyMedPhys GUI.")
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port to serve the GUI on. Defaults to Streamlit's default port.",
    )
    parser.add_argument(
        "--address",
        type=_address,
        help=(
            "Network address to serve the GUI on, for example 0.0.0.0 for "
            "every IPv4 interface. By default the GUI listens on 127.0.0.1, "
            "so only this computer can connect. WARNING: the GUI has no "
            "authentication and its apps handle patient data. Anyone who can "
            "reach this address and port can use every app and download its "
            "outputs, and the connection is unencrypted HTTP. Serve on "
            "another address only on a network where that is acceptable."
        ),
    )
    parser.add_argument("--electron", action="store_true")
    parser.set_defaults(func=main)

    return parser


def _address(value: str) -> str:
    # Streamlit treats an empty address as unset and serves on every interface.
    if not value.strip():
        raise argparse.ArgumentTypeError("the address must not be empty")
    return value
