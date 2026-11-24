# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression coverage for safe-by-default DICOM listener binding."""

import argparse

from pymedphys.cli.dicom import set_up_dicom_cli


def _parse_listen_args(*options):
    parser = argparse.ArgumentParser()
    set_up_dicom_cli(parser.add_subparsers(dest="command"))
    return parser.parse_args(["dicom", "listen", "0", *options])


def test_dicom_listener_binds_to_loopback_by_default():
    args = _parse_listen_args()
    assert args.host == "127.0.0.1"


def test_dicom_listener_allows_explicit_network_bind():
    args = _parse_listen_args("--host", "0.0.0.0")
    assert args.host == "0.0.0.0"
