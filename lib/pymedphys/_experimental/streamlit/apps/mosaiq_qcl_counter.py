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

import collections

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as st_mosaiq

CATEGORY = categories.PLANNING
TITLE = "Mosaiq QCL Counter"


def main():
    config = st_config.get_config()

    site_config_map = {}
    for site_config in config["site"]:
        site = site_config["name"]
        try:
            mosaiq_config = site_config["mosaiq"]
            qcl_location_configurations = mosaiq_config["qcl"]
            hostname = mosaiq_config["hostname"]
            port = mosaiq_config["port"]
            alias = mosaiq_config["alias"]
        except KeyError:
            continue

        qcl_locations = _extract_location_config(qcl_location_configurations)
        if len(qcl_locations) == 0:
            continue

        site_config_map[site] = {
            "locations": qcl_locations,
            "hostname": hostname,
            "port": port,
            "alias": alias,
        }

    configuration_keys = site_config_map.keys()
    if len(configuration_keys) == 0:
        st.warning(
            "The appropriate configuration items for this tool have not been provided."
        )
        st.stop()

    chosen_site = st.radio("Site", list(site_config_map.keys()))
    site_config = site_config_map[chosen_site]

    st.write(site_config)

    # connection = st_mosaiq.get_cached_mosaiq_connection()


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


def _get_staff_name(connection, staff_id):
    data = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT
            Staff.Initials,
            Staff.User_Name,
            Staff.Type,
            Staff.Category,
            Staff.Last_Name,
            Staff.First_Name
        FROM Staff
        WHERE
            TRIM(Staff.Staff_ID) = TRIM(%(staff_id)s)
        """,
        {"staff_id": staff_id},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "initials",
            "user_name",
            "type",
            "category",
            "last_name",
            "first_name",
        ],
    )

    return results


def _get_qcls_by_date(connection, location, start, end):
    data = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT
            Ident.IDA,
            Patient.Last_Name,
            Patient.First_Name,
            Chklist.Due_DtTm,
            Chklist.Act_DtTm,
            Chklist.Instructions,
            Chklist.Notes,
            QCLTask.Description
        FROM Chklist, Staff, QCLTask, Ident, Patient
        WHERE
            Chklist.Pat_ID1 = Ident.Pat_ID1 AND
            Patient.Pat_ID1 = Ident.Pat_ID1 AND
            QCLTask.TSK_ID = Chklist.TSK_ID AND
            Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
            TRIM(Staff.Last_Name) = TRIM(%(location)s) AND
            Chklist.Act_DtTm >= %(start)s AND
            Chklist.Act_DtTm < %(end)s
        """,
        {"location": location, "start": start, "end": end},
    )

    results = pd.DataFrame(
        data=data,
        columns=[
            "patient_id",
            "last_name",
            "first_name",
            "due",
            "actual_completed_time",
            "instructions",
            "comment",
            "task",
        ],
    )

    results = results.sort_values(by=["actual_completed_time"])

    return results
