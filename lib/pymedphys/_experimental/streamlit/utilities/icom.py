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
import datetime
import lzma

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys._icom.delivery as pmp_icom_delivery
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


def plot_relevant_times(relevant_times, step=5, title=None):
    raw_chart = (
        alt.Chart(relevant_times)
        .mark_bar()
        .encode(x=alt.X("datetime", bin=alt.Bin(step=step * 60 * 1000)), y="count()")
    )

    if title is not None:
        raw_chart = raw_chart.properties(title=title)

    st.altair_chart(altair_chart=raw_chart, use_container_width=True)


def get_relevant_times_for_filepaths(filepaths):
    all_relevant_times_list = collections.defaultdict(lambda: [])
    for f in filepaths:
        machine_id, relevant_times = _get_relevant_times(f)
        filepath_series = pd.Series([f] * len(relevant_times), name="filepath")

        if len(filepath_series) != len(relevant_times):
            raise ValueError("Expected length to be consistent")

        times_and_paths = pd.concat(
            [relevant_times.reset_index()["datetime"], filepath_series], axis=1
        )

        all_relevant_times_list[machine_id].append(times_and_paths)

    all_relevant_times = {}
    for key, item in all_relevant_times_list.items():
        all_relevant_times[key] = pd.concat(item, axis=0)

    return all_relevant_times


def _get_service_icom_paths(root_directory):
    service_mode_directories = [
        item.name
        for item in root_directory.glob("*")
        # TODO: Fix the hardcoding of patients to search
        if item.name.startswith("Deliver")
        or item.name.startswith("WLutz")
        or "QA" in item.name
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


@st.cache(show_spinner=False, suppress_st_warning=True)
def _get_relevant_times(filepath):
    icom_datetime, meterset, machine_id = get_icom_datetimes_meterset_machine(filepath)

    machine_id = machine_id.dropna().unique()
    if len(machine_id) > 1:
        st.write(filepath)
        st.write(machine_id)
        raise ValueError("Only one machine id per file expected")

    if len(machine_id) == 0:
        machine_id = None
        st.error(
            f"The filepath `{filepath}` has no Machine ID. "
            "This is unexpected. However, will attempt to continue "
            "despite this."
        )
    else:
        machine_id = machine_id[0]

    diff_meterset = np.concatenate([[0], np.diff(meterset)])
    relevant_rows = diff_meterset > 0
    relevant_times = icom_datetime.loc[relevant_rows]

    return machine_id, pd.Series(relevant_times, name="datetime")


@st.cache(show_spinner=False)
def get_icom_datetimes_meterset_machine(filepath):
    icom_stream = read_icom_log(filepath)

    icom_data_points = pmp_icom_extract.get_data_points(icom_stream)
    icom_datetime = pd.to_datetime(
        pd.Series([item[8:26].decode() for item in icom_data_points], name="datetime"),
        format="%Y-%m-%d%H:%M:%S",
    )
    _adjust_icom_datetime_to_remove_duplicates(icom_datetime)

    meterset = pd.Series(
        [pmp_icom_extract.extract(item, "Delivery MU")[1] for item in icom_data_points],
        name="meterset",
    )

    machine_id = pd.Series(
        [pmp_icom_extract.extract(item, "Machine ID")[1] for item in icom_data_points],
        name="machine_id",
    )

    return icom_datetime, meterset, machine_id


def _adjust_icom_datetime_to_remove_duplicates(icom_datetime):
    _, unique_index, unique_counts = np.unique(
        icom_datetime, return_index=True, return_counts=True
    )

    for index, count in zip(unique_index, unique_counts):
        if count > 1:
            time_delta = datetime.timedelta(seconds=1 / count)
            for current_duplicate, icom_index in enumerate(
                range(index + 1, index + count)
            ):
                icom_datetime.iloc[icom_index] += time_delta * (current_duplicate + 1)


# TODO: Remove "allow_output_mutation" once determine what is causing
# the issue here.
@st.cache(show_spinner=False, allow_output_mutation=True)
def get_icom_dataset(filepath):
    icom_stream = read_icom_log(filepath)
    icom_data_points = pmp_icom_extract.get_data_points(icom_stream)

    icom_datetime, meterset, machine_id = get_icom_datetimes_meterset_machine(filepath)

    raw_delivery_items = pd.DataFrame(
        [pmp_icom_delivery.get_delivery_data_items(item) for item in icom_data_points],
        columns=["meterset", "gantry", "collimator", "mlc", "jaw"],
    )
    if np.all(meterset != raw_delivery_items["meterset"]):
        raise ValueError("Expected meterset extractions to agree.")

    turn_table = pd.Series(
        [
            pmp_icom_extract.extract(item, "Table Isocentric")[1]
            for item in icom_data_points
        ],
        name="turn_table",
    )

    energy = pd.Series(
        [pmp_icom_extract.extract(item, "Energy")[1] for item in icom_data_points],
        name="energy",
    )

    interlocks = pd.Series(
        [pmp_icom_extract.extract(item, "Interlocks")[1] for item in icom_data_points],
        name="interlocks",
    )

    beam_timer = pd.Series(
        [pmp_icom_extract.extract(item, "Beam Timer")[1] for item in icom_data_points],
        name="beam_timer",
    )

    width, length, centre_x, centre_y = _determine_width_length_centre(
        raw_delivery_items["mlc"], raw_delivery_items["jaw"]
    )

    icom_dataset = pd.concat(
        [
            icom_datetime,
            machine_id,
            energy,
            width,
            length,
            raw_delivery_items[["meterset", "gantry", "collimator"]],
            turn_table,
            interlocks,
            beam_timer,
            centre_x,
            centre_y,
        ],
        axis=1,
    )

    return icom_dataset


def _get_mean_unblocked_mlc_pos(mlc, jaw):
    mlc_indices = np.arange(80)
    leaf_centre_pos = np.array((mlc_indices - 39) * 5 - 2.5)
    is_mlc_centre_blocked = np.invert(
        (-jaw[:, 0][:, None] <= leaf_centre_pos[None, :])
        & (jaw[:, 1][:, None] >= leaf_centre_pos[None, :])
    )

    mlc[is_mlc_centre_blocked, :] = np.nan
    mean_mlc = np.nanmean(mlc, axis=1)

    absolute_diff = np.abs(mlc - mean_mlc[:, None, :])
    max_absolute_diff = np.nanmax(absolute_diff, axis=1)

    mean_mlc[max_absolute_diff > 0.5] = np.nan

    return mean_mlc


def _determine_width_length_centre(mlc, jaw):
    jaw = np.array(list(jaw))
    mlc = np.array(list(mlc))

    mean_mlc = _get_mean_unblocked_mlc_pos(mlc, jaw)
    width = pd.Series(np.sum(mean_mlc, axis=1), name="width")
    length = pd.Series(jaw[:, 0] + jaw[:, 1], name="length")

    centre_x = pd.Series((mean_mlc[:, 0] - mean_mlc[:, 1]) / 2, name="centre_x")
    centre_y = pd.Series((jaw[:, 0] - jaw[:, 1]) / 2, name="centre_y")

    length.loc[np.isnan(width)] = np.nan
    centre_x.loc[np.isnan(width)] = np.nan
    centre_y.loc[np.isnan(width)] = np.nan

    return width, length, centre_x, centre_y
