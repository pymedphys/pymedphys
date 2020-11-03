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

from pymedphys._imports import streamlit as st

from pymedphys._streamlit import config as st_config


@st.cache
def get_dicom_export_locations():
    site_directories = st_config.get_site_directories()
    dicom_export_locations = {
        site: directories["monaco"].parent.parent.joinpath("DCMXprtFile")
        for site, directories in site_directories.items()
    }

    return dicom_export_locations


@st.cache
def get_icom_live_stream_directories():
    config = st_config.get_config()
    icom_live_stream_directories = {}
    for site in config["site"]:
        icom_live_base_directory = pathlib.Path(site["export-directories"]["icom_live"])
        for linac in site["linac"]:
            icom_live_stream_directories[linac["name"]] = str(
                icom_live_base_directory.joinpath(linac["ip"])
            )

    return icom_live_stream_directories


@st.cache
def get_machine_centre_map():
    config = st_config.get_config()
    machine_centre_map = {}
    for site in config["site"]:
        for linac in site["linac"]:
            machine_centre_map[linac["name"]] = site["name"]

    return machine_centre_map


@st.cache
def get_mosaiq_details():
    config = st_config.get_config()
    mosaiq_details = {
        site["name"]: {
            "timezone": site["mosaiq"]["timezone"],
            "server": f'{site["mosaiq"]["hostname"]}:{site["mosaiq"]["port"]}',
        }
        for site in config["site"]
    }

    return mosaiq_details


@st.cache
def get_default_icom_directories():
    config = st_config.get_config()
    default_icom_directory = config["icom"]["patient_directories"]

    return default_icom_directory


@st.cache
def get_default_gamma_options():
    config = st_config.get_config()
    default_gamma_options = config["gamma"]

    return default_gamma_options


@st.cache
def get_logfile_root_dir():
    config = st_config.get_config()
    logfile_root_dir = pathlib.Path(config["trf_logfiles"]["root_directory"])

    return logfile_root_dir


@st.cache
def get_indexed_backups_directory():
    logfile_root_dir = get_logfile_root_dir()
    indexed_backups_directory = logfile_root_dir.joinpath("diagnostics/already_indexed")

    return indexed_backups_directory


@st.cache
def get_indexed_trf_directory():
    logfile_root_dir = get_logfile_root_dir()
    indexed_trf_directory = logfile_root_dir.joinpath("indexed")

    return indexed_trf_directory


def get_gamma_options(advanced_mode_local):
    default_gamma_options = get_default_gamma_options()

    if advanced_mode_local:
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
