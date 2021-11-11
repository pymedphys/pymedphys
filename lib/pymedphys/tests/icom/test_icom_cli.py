# Copyright (C) 2021 Radiotherapy AI Pty Ltd

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import lzma
import multiprocessing
import os
import pathlib
import socket
import subprocess
import sys
import tempfile

import pytest

from pymedphys._data import download
from pymedphys._root import LIBRARY_ROOT


@pytest.mark.skipif(
    sys.platform == "win32", reason="Does not currently work on Windows"
)
def test_icom_cli():
    icom_server_process = multiprocessing.Process(target=_mock_icom_server)
    icom_server_process.start()

    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        FROZEN_BINARY_DIRECTORY = LIBRARY_ROOT.parents[1]
        env["PATH"] = str(FROZEN_BINARY_DIRECTORY) + os.pathsep + env["PATH"]

    with tempfile.TemporaryDirectory() as temp_dir:
        icom_listen_cli = subprocess.Popen(
            ["pymedphys", "icom", "listen", "127.0.0.1", temp_dir], env=env
        )
        icom_server_process.join()
        icom_listen_cli.terminate()

        live_files = list(pathlib.Path(temp_dir).glob("**/*.txt"))
        assert len(live_files) == 256


def _mock_icom_server():
    paths = download.zip_data_paths("metersetmap-gui-e2e-data.zip")
    icom_paths = [path for path in paths if path.suffix == ".xz"]

    def load_icom_stream(icom_path):
        with lzma.open(icom_path, "r") as f:
            contents = f.read()

        return contents

    data = load_icom_stream(icom_paths[0])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 1706))
        s.listen()
        conn, _addr = s.accept()
        with conn:
            conn.sendall(data)
