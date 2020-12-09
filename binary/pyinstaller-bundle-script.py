# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import sys
import pathlib
import tarfile
import shutil

PYMEDPHYS_BAT_NAME = "pymedphys.bat"


def main():
    """The script that boots when PyMedPhysGUI-vX.Y.Z.exe is run.

    This script checks to see if the required PyMedPhys files have been
    installed within the current working directory. If they have not
    it extracts them.

    Once the embedded Python distribution is provisioned this boots up
    the PyMedPhys streamlit app.

    Note
    ----
    This script will run with pyinstaller's Python install. However, no
    external libraries are installed within this Python instance.
    PyMedPhys itself is stored within ``python-embed/Lib/site-packages``.
    The Python within ``python-embed`` is not the same Python install
    that pyinstaller is using to run this script.

    """
    cwd = pathlib.Path(os.getcwd())
    installation_path = cwd.joinpath("python-embed")
    pymedphys_bat = cwd.joinpath(PYMEDPHYS_BAT_NAME)

    if not pymedphys_bat.exists():
        _install(cwd, installation_path)

    _boot_streamlit_app(installation_path)


def _install(cwd, installation_path):
    """Extract the Python embedded environment to the current working directory.

    Note
    ----
    The ``pymedphys.bat`` is extracted last, as this is used to test
    whether or not the install was completed.

    """
    pyinstaller_temp_dir = pathlib.Path(
        sys._MEIPASS  # pylint: disable = no-member, protected-access
    )
    data_path = pyinstaller_temp_dir.joinpath("data")

    python_xztar = data_path.joinpath("python-embed.tar.xz")

    installation_path.mkdir()

    with tarfile.open(python_xztar) as f:
        f.extractall(installation_path)

    for f in ["LICENSE", PYMEDPHYS_BAT_NAME]:
        shutil.copy(data_path.joinpath(f), cwd.joinpath(f))


def _boot_streamlit_app(python_embedded_directory):
    """Starts the PyMedPhys GUI within the Python embedded distribution.

    Parameters
    ----------
    python_embedded_directory
        The full path to the Python embedded distribution.

    """
    subprocess.check_call(
        "python.exe -m pymedphys gui", cwd=python_embedded_directory, shell=True
    )


if __name__ == "__main__":
    main()
