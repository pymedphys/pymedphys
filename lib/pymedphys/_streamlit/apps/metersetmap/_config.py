# Copyright (C) 2020-2021 Cancer Care Associates

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

from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._streamlit.utilities import config as st_config

HERE = pathlib.Path(__file__).parent


def config_on_disk():
    return None


def config_in_current_directory():
    return HERE


@st.cache
def download_demo_files():
    cwd = pathlib.Path.cwd()
    pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip", extract_directory=cwd)

    return cwd.joinpath("pymedphys-gui-demo")


CONFIG_OPTIONS = {
    "Config on Disk": config_on_disk,
    "File Upload/Download Only": config_in_current_directory,
    "Demo Data": download_demo_files,
}


def get_config(config_mode):
    path = CONFIG_OPTIONS[config_mode]()

    return st_config.get_config(path)


@st.cache
def get_dicom_export_locations(config):
    site_directories = st_config.get_site_directories(config)
    dicom_export_locations = {
        site: directories["monaco"].parent.parent.joinpath("DCMXprtFile")
        for site, directories in site_directories.items()
    }

    return dicom_export_locations


@st.cache
def get_icom_live_stream_directories(config):
    icom_live_stream_directories = {}
    for site in config["site"]:
        icom_live_base_directory = pathlib.Path(site["export-directories"]["icom_live"])
        for linac in site["linac"]:
            icom_live_stream_directories[linac["name"]] = str(
                icom_live_base_directory.joinpath(linac["ip"])
            )

    return icom_live_stream_directories


@st.cache
def get_machine_centre_map(config):
    machine_centre_map = {}
    for site in config["site"]:
        for linac in site["linac"]:
            machine_centre_map[linac["name"]] = site["name"]

    return machine_centre_map


def _get_alias_with_fallback(site_mosaiq_config):
    try:
        return site_mosaiq_config["alias"]
    except KeyError:
        pass

    try:
        port = site_mosaiq_config["port"]
    except KeyError:
        port = 1433

    return f"{site_mosaiq_config['hostname']}:{port}"


@st.cache
def get_mosaiq_details(config):
    mosaiq_details = {
        site["name"]: {
            "timezone": site["mosaiq"]["timezone"],
            "server": {
                "hostname": site["mosaiq"]["hostname"],
                "port": site["mosaiq"]["port"],
                "alias": _get_alias_with_fallback(site["mosaiq"]),
            },
        }
        for site in config["site"]
    }

    return mosaiq_details


@st.cache
def get_default_icom_directories(config):
    default_icom_directory = config["icom"]["patient_directories"]

    return default_icom_directory


@st.cache
def get_default_gamma_options(config):
    default_gamma_options = config["gamma"]

    return default_gamma_options


@st.cache
def get_logfile_root_dir(config):
    logfile_root_dir = pathlib.Path(config["trf_logfiles"]["root_directory"])

    return logfile_root_dir


@st.cache
def get_indexed_backups_directory(config):
    logfile_root_dir = get_logfile_root_dir(config)
    indexed_backups_directory = logfile_root_dir.joinpath("diagnostics/already_indexed")

    return indexed_backups_directory


@st.cache
def get_indexed_trf_directory(config):
    logfile_root_dir = get_logfile_root_dir(config)
    indexed_trf_directory = logfile_root_dir.joinpath("indexed")

    return indexed_trf_directory


def get_gamma_options(config, advanced_mode):
    default_gamma_options = get_default_gamma_options(config)

    if advanced_mode:
        st.sidebar.markdown(
            """
            # Gamma parameters
            """
        )
        result = {
            **default_gamma_options,
            **{
                "dose_percent_threshold": st.sidebar.number_input(
                    "MU Percent Threshold",
                    value=default_gamma_options["dose_percent_threshold"],
                ),
                "distance_mm_threshold": st.sidebar.number_input(
                    "Distance (mm) Threshold",
                    value=default_gamma_options["distance_mm_threshold"],
                ),
                "local_gamma": st.sidebar.checkbox(
                    "Local Gamma", default_gamma_options["local_gamma"]
                ),
                "max_gamma": st.sidebar.number_input(
                    "Max Gamma", value=default_gamma_options["max_gamma"]
                ),
            },
        }
    else:
        result = default_gamma_options

    return result
