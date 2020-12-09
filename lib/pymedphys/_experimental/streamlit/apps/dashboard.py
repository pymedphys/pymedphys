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
from pymedphys._streamlit.utilities import mosaiq as st_mosaiq


def main():
    st.write("# Mosaiq QCL Dashboard")

    centres = ["rccc", "nbcc", "sash"]
    # centres = ["nbcc"]
    servers = {
        "rccc": "msqsql",
        "nbcc": "physics-server:31433",
        "sash": "physics-server",
    }
    physics_locations = {
        "rccc": "Physics_Check",
        "nbcc": "Physics",
        "sash": "Physics_Check",
    }

    cursors = {
        centre: st_mosaiq.get_mosaiq_cursor_in_bucket(servers[centre])
        for centre in centres
    }

    if st.button("Refresh"):
        st.experimental_rerun()

    for centre in centres:
        st.write(f"## {centre.upper()}")

        cursor_bucket = cursors[centre]
        physics_location = physics_locations[centre]

        try:
            table = msq_helpers.get_incomplete_qcls(
                cursor_bucket["cursor"], physics_location
            )
        except (pymssql.InterfaceError, pymssql.OperationalError) as e:
            st.write(e)
            cursor_bucket["cursor"] = st_mosaiq.uncached_get_mosaiq_cursor(
                servers[centre]
            )
            table = msq_helpers.get_incomplete_qcls(
                cursor_bucket["cursor"], physics_location
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
