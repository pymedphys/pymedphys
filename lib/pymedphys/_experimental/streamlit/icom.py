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

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._streamlit.utilities import misc


def main():
    st.title("iCom Logs Explorer")
    _, icom_directory = misc.get_site_and_directory("Site", "icom")

    icom_patients_directory = icom_directory.joinpath("patients")

    st.write(icom_patients_directory)

    patient_directories = [
        item.name for item in icom_patients_directory.glob("*") if item != "archive"
    ]

    service_mode = st.checkbox("Focus on Service Mode Fields", True)

    if not service_mode:
        st.write(ValueError("Not yet implemented"))
        st.stop()

    service_mode_directories = [
        item for item in patient_directories if item.startswith("Deliver")
    ]

    service_icom_logs = []
    for directory in service_mode_directories:
        full_path = icom_patients_directory.joinpath(directory)
        service_icom_logs += list(full_path.glob("*.xz"))

    service_icom_logs = pd.Series(service_icom_logs, name="filepath")

    filestems = pd.Series([item.stem for item in service_icom_logs], name="filestem")
    timestamps = pd.Series(
        pd.to_datetime(filestems, format="%Y%m%d_%H%M%S"), name="datetime"
    )

    path_dataframe = pd.concat([service_icom_logs, filestems, timestamps], axis=1)

    timestamp_dates = timestamps.dt.date

    dates = pd.Series(pd.unique(timestamp_dates)).sort_values(ascending=False)
    selected_date = st.selectbox("Date", list(dates))

    selected_paths_by_date = path_dataframe.loc[selected_date == timestamp_dates]
    selected_paths_by_date = selected_paths_by_date.sort_values(
        "datetime", ascending=False
    )

    st.write(selected_paths_by_date)

    times = selected_paths_by_date["datetime"].dt.time
    selected_time = st.selectbox("Time", list(times))

    selected_path_by_time = selected_paths_by_date.loc[selected_time == times]

    if len(selected_path_by_time["filepath"]) != 1:
        raise ValueError("Only one filepath per time supported")

    filepath = selected_path_by_time["filepath"].iloc[0]

    st.write(filepath)
