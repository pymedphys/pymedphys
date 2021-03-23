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


from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config

CATEGORY = categories.PLANNING
TITLE = "Mosaiq QCL Counter"


def main():
    config = st_config.get_config()

    site_config_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            mosaiq_config = config["mosaiq"]
            qcl_location_configurations = mosaiq_config["qcl"]
        except KeyError:
            continue

        qcl_locations = _extract_location_config(qcl_location_configurations)
        if len(qcl_locations) == 0:
            continue

        site_config_map[site] = qcl_locations

    configuration_keys = site_config_map.keys()
    if len(configuration_keys) == 0:
        st.warning(
            "The appropriate configuration items for this tool have not been provided."
        )
        st.stop()

    chosen_site = st.radio("Site", list(site_config_map.keys()))
    site_config = site_config_map[chosen_site]


def _extract_location_config(qcl_location_configurations):
    qcl_locations = {}
    for qcl_location_config in qcl_location_configurations:
        try:
            location = qcl_location_config["location"]
            count = qcl_location_config["count"]
            tasks = qcl_location_config["tasks"]

            qcl_locations[location] = {
                "count": count,
                "tasks": tasks,
            }
        except KeyError:
            continue

    return qcl_locations
