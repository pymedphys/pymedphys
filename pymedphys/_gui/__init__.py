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
import subprocess

HERE = pathlib.Path(__file__).parent.resolve()
STREAMLIT_CONTENT_DIR = HERE.joinpath("streamlit")


def fill_streamlit_credentials():
    streamlit_config_dir = pathlib.Path.home().joinpath(".streamlit")
    streamlit_config_dir.mkdir(exist_ok=True)

    template_streamlit_credentials_file = STREAMLIT_CONTENT_DIR.joinpath(
        "credentials.toml"
    )
    new_credential_file = streamlit_config_dir.joinpath("credentials.toml")

    try:
        shutil.copy2(template_streamlit_credentials_file, new_credential_file)
    except FileExistsError:
        pass


def main(_):
    fill_streamlit_credentials()

    streamlit_script_path = str(STREAMLIT_CONTENT_DIR.joinpath("mudensity-compare.py"))
    subprocess.check_call(
        " ".join(["streamlit", "run", streamlit_script_path]), shell=True
    )
