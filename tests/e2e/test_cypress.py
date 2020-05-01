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

import pathlib
import subprocess
from contextlib import contextmanager

import pytest

import psutil
import pymedphys


@contextmanager
def process(*args, **kwargs):
    proc = subprocess.Popen(*args, **kwargs)
    try:
        yield proc
    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            child.kill()
        proc.kill()


HERE = pathlib.Path(__file__).parent.resolve()


@pytest.mark.yarn
def test_streamlit_gui():
    pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=HERE)

    with process("poetry run pymedphys gui", cwd=HERE, shell=True) as _:
        subprocess.check_call("yarn", cwd=HERE, shell=True)
        subprocess.check_call("yarn cypress run", cwd=HERE, shell=True)


if __name__ == "__main__":
    test_streamlit_gui()
