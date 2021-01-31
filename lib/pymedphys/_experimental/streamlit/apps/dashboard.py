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
from pymedphys._streamlit.utilities import mosaiq as st_mosaiq

CATEGORY = categories.ALPHA
TITLE = "Clinical Dashboard"


def main():
    centres = ["rccc", "nbcc", "sash"]
    # centres = ["nbcc"]
    servers = {
        "rccc": {"hostname": "msqsql", "alias": "RCCC Mosaiq SQL Server"},
        "nbcc": {
            "hostname": "rccc-physicssvr",
            "port": 31433,
            "alias": "NBCC Mosaiq SQL Server",
        },
        "sash": {"hostname": "rccc-physicssvr", "alias": "SASH Mosaiq SQL Server"},
    }
    physics_locations = {
        "rccc": "Physics_Check",
        "nbcc": "Physics",
        "sash": "Physics_Check",
    }

    connections = {
        centre: st_mosaiq.get_cached_mosaiq_connection_in_dict(**servers[centre])
        for centre in centres
    }

    if st.button("Refresh"):
        st.experimental_rerun()

    for centre in centres:
        st.write(f"## {centre.upper()}")

        connection_bucket = connections[centre]
        physics_location = physics_locations[centre]

        try:
            table = msq_helpers.get_incomplete_qcls(
                connection_bucket["connection"], physics_location
            )
        except (pymssql.InterfaceError, pymssql.OperationalError) as e:
            st.write(e)
            connection_bucket["connection"] = st_mosaiq.get_uncached_mosaiq_connection(
                **servers[centre]
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
