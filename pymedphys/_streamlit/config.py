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


import functools
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


def get_monaco_from_site_config(site_config):
    return pathlib.Path(site_config["monaco"]["focaldata"]).joinpath(
        site_config["monaco"]["clinic"]
    )


def get_export_directory_from_site_config(site_config, export_directory):
    return pathlib.Path(site_config["export-directories"][export_directory])


@st.cache
def get_site_directories():
    config = get_config()

    site_directory_functions = {
        "monaco": get_monaco_from_site_config,
        "escan": functools.partial(
            get_export_directory_from_site_config, export_directory="escan"
        ),
        "anonymised_monaco": functools.partial(
            get_export_directory_from_site_config, export_directory="anonymised_monaco"
        ),
    }

    site_directories = {}
    for site in config["site"]:
        site_name = site["name"]
        site_directories[site_name] = {}

        for key, func in site_directory_functions.items():
            try:
                site_directories[site_name][key] = func(site)
            except KeyError:
                pass

    return site_directories
