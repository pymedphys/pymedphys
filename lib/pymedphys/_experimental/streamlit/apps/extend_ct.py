# Copyright (C) 2021 Cancer Care Associates

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
import re

from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config

CATEGORY = categories.PLANNING
TITLE = "Monaco Extend CT"


def main():
    config = st_config.get_config()

    site_directory_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            site_directory_map[site] = {
                "focal_data": site_config["monaco"]["focaldata"],
                "hostname": site_config["monaco"]["hostname"],
                "port": site_config["monaco"]["dicom_port"],
            }
        except KeyError:
            continue

    chosen_site = st.radio("Site", list(site_directory_map.keys()))
    directories = site_directory_map[chosen_site]

    focal_data = pathlib.Path(directories["focal_data"])
    dicom_export = focal_data.joinpath("DCMXprtFile")

    # Caps or not within glob doesn't matter on Windows, but it does
    # matter on *nix systems.
    dicom_files = dicom_export.glob("*.DCM")

    patient_id_pattern = re.compile(r"(\d+)_.*\d\d\d\d\d.DCM")
    patient_ids = {
        patient_id_pattern.match(path.name).group(1)
        for path in dicom_files
        if patient_id_pattern.match(path.name)
    }

    st.write(patient_ids)
