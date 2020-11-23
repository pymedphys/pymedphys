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


def get_paths_by_date(icom_patients_directory, selected_date=None):
    service_icom_paths = _get_service_icom_paths(icom_patients_directory)
    timestamps = _get_file_datetimes(service_icom_paths)

    path_dataframe = pd.concat([service_icom_paths, timestamps], axis=1)
    timestamp_dates = timestamps.dt.date

    dates = pd.Series(pd.unique(timestamp_dates)).sort_values(ascending=False)

    if selected_date is None:
        selected_date = st.selectbox("Date", list(dates))

    selected_paths_by_date = path_dataframe.loc[selected_date == timestamp_dates]
    selected_paths_by_date = selected_paths_by_date.sort_values(
        "datetime", ascending=False
    )

    return selected_paths_by_date


def _get_service_icom_paths(root_directory):
    service_mode_directories = [
        item.name
        for item in root_directory.glob("*")
        if item.name.startswith("Deliver")
    ]

    service_icom_paths = []
    for directory in service_mode_directories:
        full_path = root_directory.joinpath(directory)
        service_icom_paths += list(full_path.glob("*.xz"))

    service_icom_paths = pd.Series(service_icom_paths, name="filepath")

    return service_icom_paths


def _get_file_datetimes(icom_paths):
    filestems = pd.Series([item.stem for item in icom_paths], name="filestem")
    timestamps = pd.Series(
        pd.to_datetime(filestems, format="%Y%m%d_%H%M%S"), name="datetime"
    )

    return timestamps
