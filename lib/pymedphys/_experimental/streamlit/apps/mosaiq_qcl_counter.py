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

import datetime
import time

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

    configuration_keys = site_config_map.keys()
    if len(configuration_keys) == 0:
        st.warning(
            "The appropriate configuration items for this tool have not been provided."
        )
        st.stop()

    chosen_site = st.radio("Site", list(site_config_map.keys()))
    site_config = site_config_map[chosen_site]
    connection_config = {k: site_config[k] for k in ("hostname", "port", "alias")}
    location = site_config["location"]

    connection = st_mosaiq.get_cached_mosaiq_connection(**connection_config)

    st.write("## Filters")

    st.write(
        """
        ### Date range

        Defaults to between the start of last month and the start of
        the current month.
        """
    )

    now = datetime.datetime.now()

    start_of_month = _get_start_of_month(now)
    start_of_last_month = _get_start_of_last_month(now)

    left, right = st.beta_columns(2)

    chosen_start = left.date_input("Start date", value=start_of_last_month)
    chosen_end = right.date_input("End date", value=start_of_month)

    results = _get_qcls_by_date(connection, location, chosen_start, chosen_end)
    st.write(results)


def _get_start_of_month(dt: datetime.datetime):
    return dt.replace(day=1)


# def _get_start_of_next_month(dt: datetime.datetime):
#     definitely_in_next_month = _get_start_of_month(dt) + datetime.timedelta(days=32)
#     return _get_start_of_month(definitely_in_next_month)


def _get_start_of_last_month(dt: datetime.datetime):
    definitely_in_last_month = _get_start_of_month(dt) - datetime.timedelta(days=1)
    return _get_start_of_month(definitely_in_last_month)


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
            RTRIM(LTRIM(Staff.Last_Name)) = RTRIM(LTRIM(%(location)s)) AND
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
