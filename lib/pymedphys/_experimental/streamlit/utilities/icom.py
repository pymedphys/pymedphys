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
import lzma

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys._icom.extract as pmp_icom_extract


def read_icom_log(filepath):
    with lzma.open(filepath, "r") as f:
        icom_stream = f.read()

    return icom_stream


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


def plot_all_relevant_times(all_relevant_times):
    for key, data in all_relevant_times.items():
        st.write(f"### Machine ID: `{key}`")

        plot_relevant_times(data)


def plot_relevant_times(relevant_times):
    relevant_times = pd.DataFrame(
        pd.concat(relevant_times, axis=0), columns=["datetime"]
    )

    raw_chart = (
        alt.Chart(relevant_times)
        .mark_bar()
        .encode(x=alt.X("datetime", bin=alt.Bin(step=5 * 60 * 1000)), y="count()")
    )

    st.altair_chart(altair_chart=raw_chart, use_container_width=True)


def get_relevant_times_for_filepaths(filepaths):
    all_relevant_times = collections.defaultdict(lambda: [])
    for f in filepaths:
        machine_id, relevant_times = _get_relevant_times(f)
        all_relevant_times[machine_id].append(relevant_times)

    return all_relevant_times


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


@st.cache(show_spinner=False)
def _get_relevant_times(filepath):
    icom_datetime, meterset, machine_id = get_icom_datetimes_meterset_machine(filepath)

    machine_id = machine_id.unique()
    if len(machine_id) != 1:
        raise ValueError("Only one machine id per file expected")

    machine_id = machine_id[0]

    diff_meterset = np.concatenate([[0], np.diff(meterset)])
    relevant_rows = diff_meterset > 0
    relevant_times = icom_datetime.loc[relevant_rows]

    return machine_id, pd.Series(relevant_times.unique(), name="datetime")


def _get_meterset_timestep_weighting(delivery):
    meterset = np.array(delivery.mu)

    diff_meterset = np.concatenate([[0], np.diff(meterset)])
    timestep_meterset_weighting = diff_meterset / meterset[-1]

    if not np.allclose(np.sum(timestep_meterset_weighting), 1):
        raise ValueError("Meterset position weighting should add up to 1")

    return timestep_meterset_weighting


@st.cache(show_spinner=False)
def get_icom_datetimes_meterset_machine(filepath):
    icom_stream = read_icom_log(filepath)

    icom_data_points = pmp_icom_extract.get_data_points(icom_stream)
    icom_datetime = pd.to_datetime(
        pd.Series([item[8:26].decode() for item in icom_data_points], name="datetime"),
        format="%Y-%m-%d%H:%M:%S",
    )

    meterset = pd.Series(
        [pmp_icom_extract.extract(item, "Delivery MU")[1] for item in icom_data_points],
        name="meterset",
    )

    machine_id = pd.Series(
        [pmp_icom_extract.extract(item, "Machine ID")[1] for item in icom_data_points],
        name="machine_id",
    )

    return icom_datetime, meterset, machine_id
