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

import psutil
import pytest

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
PYMEDPHYS_LIB_DIR = HERE.joinpath("..", "..").resolve()
STREAMLIT_GUI_DIR = PYMEDPHYS_LIB_DIR.joinpath("_gui", "streamlit")


@pytest.mark.yarn
def test_mudensity_compare_gui():
    pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=HERE)

    with process("poetry run pymedphys gui", cwd=HERE, shell=True) as _:
        subprocess.check_call("yarn", cwd=HERE, shell=True)

        subprocess.check_call(
            "yarn cypress run --spec cypress/integration/streamlit/mudensity-compare.spec.js",
            cwd=HERE,
            shell=True,
        )


@pytest.mark.yarn
def test_pseudonymise():
    with process(
        "poetry run streamlit run pseudonymise.py", cwd=STREAMLIT_GUI_DIR, shell=True
    ) as _:
        subprocess.check_call("yarn", cwd=HERE, shell=True)

        subprocess.check_call(
            "yarn cypress run --spec cypress/integration/streamlit/pseudonymisation.spec.js",
            cwd=HERE,
            shell=True,
        )
