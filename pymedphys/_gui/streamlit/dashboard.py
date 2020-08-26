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


# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import pymssql

import streamlit as st

from pymedphys._mosaiq import helpers as msq_helpers
from pymedphys._streamlit import mosaiq as st_mosaiq
from pymedphys._streamlit import rerun as st_rerun

st_rerun.autoreload([st_mosaiq, st_rerun, msq_helpers])

centres = ["rccc", "nbcc", "sash"]
servers = {"rccc": "msqsql", "nbcc": "physics-server:31433", "sash": "physics-server"}
physics_locations = {
    "rccc": "Physics_Check",
    "nbcc": "Physics",
    "sash": "Physics_Check",
}

cursors = {
    centre: st_mosaiq.get_mosaiq_cursor_in_bucket(servers[centre]) for centre in centres
}

"# Mosaiq QCLs"

if st.button("Refresh"):
    st_rerun.rerun()

for centre in centres:
    f"## {centre.upper()}"

    cursor_bucket = cursors[centre]
    physics_location = physics_locations[centre]

    try:
        table = msq_helpers.get_incomplete_qcls(
            cursor_bucket["cursor"], physics_location
        )
    except (pymssql.InterfaceError, pymssql.OperationalError) as e:
        st.write(e)
        cursor_bucket["cursor"] = st_mosaiq.uncached_get_mosaiq_cursor(servers[centre])
        table = msq_helpers.get_incomplete_qcls(
            cursor_bucket["cursor"], physics_location
        )

    for index, row in table.iterrows():
        patient_header = (
            f"### `{row.patient_id}` {str(row.last_name).upper()}, "
            f"{str(row.first_name).lower().capitalize()}"
        )
        st.write(patient_header)

        f"Due: `{row.due}`"
        if row.instructions:
            f"Instructions: `{row.instructions}`"

        if row.comment:
            f"Comment: `{row.comment}`"

        f"Task: `{row.task}`"
