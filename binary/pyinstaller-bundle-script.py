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


def boot_streamlit_app(installation_path):
    subprocess.check_call(
        "python.exe -m pymedphys gui", cwd=installation_path, shell=True
    )


def main():
    cwd = pathlib.Path(os.getcwd())
    installation_path = cwd.joinpath("python-embed")

    if installation_path.exists():
        boot_streamlit_app(installation_path)
    else:
        pyinstaller_temp_dir = pathlib.Path(
            sys._MEIPASS  # pylint: disable = no-member, protected-access
        )
        data_path = pyinstaller_temp_dir.joinpath("data")

        for filename in ["resolve-path.cmd", "pymedphys.bat"]:
            shutil.copy(data_path.joinpath(filename), cwd.joinpath(filename))

        python_xztar = data_path.joinpath("python-embed.tar.xz")

        installation_path.mkdir()

        with tarfile.open(python_xztar) as f:
            f.extractall(installation_path)

        boot_streamlit_app(installation_path)


if __name__ == "__main__":
    main()
