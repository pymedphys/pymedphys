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

import streamlit as st

import pymedphys
from pymedphys import _config as pmp_config


def download_and_extract_demo_data(cwd):
    pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=cwd)


@st.cache
def get_config():
    try:
        result = pmp_config.get_config()
    except FileNotFoundError:
        cwd = pathlib.Path.cwd()
        download_and_extract_demo_data(cwd)
        result = pmp_config.get_config(cwd.joinpath("pymedphys-gui-demo"))

    return result


@st.cache
def get_site_directories():
    config = get_config()
    site_directories = {
        site["name"]: {
            "monaco": pathlib.Path(site["monaco"]["focaldata"]).joinpath(
                site["monaco"]["clinic"]
            ),
            "escan": pathlib.Path(site["export-directories"]["escan"]),
            "anonymised_monaco": pathlib.Path(
                site["export-directories"]["anonymised_monaco"]
            ),
        }
        for site in config["site"]
    }

    return site_directories
