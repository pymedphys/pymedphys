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


@st.cache_data
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


@st.cache_data
def get_dicom_export_locations(config):
    site_directories = st_config.get_site_directories(config)
    dicom_export_locations = {
        site: directories["monaco"].parent.parent.joinpath("DCMXprtFile")
        for site, directories in site_directories.items()
    }

    return dicom_export_locations


@st.cache_data
def get_icom_live_stream_directories(config):
    icom_live_stream_directories = {}
    for site in config["site"]:
        icom_live_base_directory = pathlib.Path(site["export-directories"]["icom_live"])
        for linac in site["linac"]:
            icom_live_stream_directories[linac["name"]] = str(
                icom_live_base_directory.joinpath(linac["ip"])
            )

    return icom_live_stream_directories


@st.cache_data
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


@st.cache_data
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


@st.cache_data
def get_default_icom_directories(config):
    default_icom_directory = config["icom"]["patient_directories"]

    return default_icom_directory


# The names that the [gamma] table used before version 0.42.0, with the option
# of pymedphys.gamma that each one sets. Existing configuration files, and
# the demo data, still use them.
_EARLIER_GAMMA_KEYS = {
    "dose_percent_threshold": "dose_criterion_percent",
    "distance_mm_threshold": "distance_criterion_mm",
    "lower_percent_dose_cutoff": "lower_dose_cutoff_percent",
    "global_normalisation": "normalisation_dose",
    "max_gamma": "gamma_cap",
    "interp_algo": "interpolator",
    "ram_available": "memory_budget_bytes",
}


def gamma_options_from_table(table):
    """The options for ``pymedphys.gamma`` that a ``[gamma]`` table sets.

    The table may use the option names of ``pymedphys.gamma``, or the names
    it used before version 0.42.0.
    """
    options = {}
    for key, value in table.items():
        if key == "quiet":
            # Gamma reports its progress through logging.
            continue
        if key == "local_gamma":
            key, value = "normalisation", "local" if value else "global"
        elif key == "interp_fraction":
            key, value = "search_step_fraction", 1 / value
        else:
            key = _EARLIER_GAMMA_KEYS.get(key, key)

        if key in options:
            raise ValueError(
                f"The [gamma] table of the configuration sets {key} twice: "
                "under that name, and under the name it had before version "
                "0.42.0."
            )
        options[key] = value

    return options


@st.cache_data
def get_default_gamma_options(config):
    return gamma_options_from_table(config["gamma"])


@st.cache_data
def get_logfile_root_dir(config):
    logfile_root_dir = pathlib.Path(config["trf_logfiles"]["root_directory"])

    return logfile_root_dir


@st.cache_data
def get_indexed_backups_directory(config):
    logfile_root_dir = get_logfile_root_dir(config)
    indexed_backups_directory = logfile_root_dir.joinpath("diagnostics/already_indexed")

    return indexed_backups_directory


@st.cache_data
def get_indexed_trf_directory(config):
    logfile_root_dir = get_logfile_root_dir(config)
    indexed_trf_directory = logfile_root_dir.joinpath("indexed")

    return indexed_trf_directory


def get_gamma_options(config, advanced_mode):
    default_gamma_options = get_default_gamma_options(config)

    if not advanced_mode:
        return default_gamma_options

    st.sidebar.markdown(
        """
        # Gamma parameters
        """
    )
    dose_criterion_percent = st.sidebar.number_input(
        "MU criterion (%)", value=default_gamma_options["dose_criterion_percent"]
    )
    distance_criterion_mm = st.sidebar.number_input(
        "Distance criterion (mm)",
        value=default_gamma_options["distance_criterion_mm"],
    )
    local_normalisation = st.sidebar.checkbox(
        "Local normalisation",
        default_gamma_options.get("normalisation", "global") == "local",
    )
    gamma_cap = st.sidebar.number_input(
        "Gamma cap", value=default_gamma_options.get("gamma_cap")
    )

    return {
        **default_gamma_options,
        "dose_criterion_percent": dose_criterion_percent,
        "distance_criterion_mm": distance_criterion_mm,
        "normalisation": "local" if local_normalisation else "global",
        "gamma_cap": gamma_cap,
    }
