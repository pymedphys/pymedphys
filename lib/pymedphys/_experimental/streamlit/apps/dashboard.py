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

import collections

from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql
from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import helpers as msq_helpers
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as st_mosaiq

CATEGORY = categories.ALPHA
TITLE = "Clinical Dashboard"


def main():
    config = st_config.get_config()

    site_config_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            mosaiq_config = site_config["mosaiq"]
            location = mosaiq_config["physics_qcl_location"]
            hostname = mosaiq_config["hostname"]
            port = mosaiq_config["port"]
            alias = mosaiq_config["alias"]
        except KeyError:
            continue

        site_config_map[site] = {
            "location": location,
            "hostname": hostname,
            "port": port,
            "alias": alias,
        }

    centres = list(site_config_map.keys())
    connection_config = {
        site: {k: site_config[k] for k in ("hostname", "port", "alias")}
        for site, site_config in site_config_map.items()
    }

    connections = {
        centre: st_mosaiq.get_cached_mosaiq_connection_in_dict(
            **connection_config[centre]
        )
        for centre in centres
    }

    if st.button("Refresh"):
        st.experimental_rerun()

    for centre in centres:
        st.write(f"## {centre.upper()}")

        connection_bucket = connections[centre]
        physics_location = site_config_map[centre]["location"]

        try:
            table = msq_helpers.get_incomplete_qcls(
                connection_bucket["connection"], physics_location
            )
        except (pymssql.InterfaceError, pymssql.OperationalError):
            connection_bucket["connection"] = st_mosaiq.get_uncached_mosaiq_connection(
                **connection_config[centre]
            )
            table = msq_helpers.get_incomplete_qcls(
                connection_bucket["connection"], physics_location
            )

        table_dict = collections.OrderedDict()

        for index, row in table.iterrows():
            patient_name = f"{str(row.last_name).upper()}, {str(row.first_name).lower().capitalize()}"

            table_dict[index] = collections.OrderedDict(
                {
                    "Due": row.due.strftime("%Y-%m-%d"),
                    "Patient": f"{row.patient_id} {patient_name}",
                    "Instructions": row.instructions,
                    "Comment": row.comment,
                    "Task": row.task,
                }
            )

        formated_table = pd.DataFrame.from_dict(table_dict).T
        formated_table = formated_table.reindex(
            ["Due", "Patient", "Instructions", "Comment", "Task"], axis=1
        )

        st.write(formated_table)
