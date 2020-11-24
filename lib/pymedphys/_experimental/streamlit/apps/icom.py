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

import datetime

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys._icom.delivery as pmp_icom_delivery
import pymedphys._icom.extract as pmp_icom_extract
from pymedphys._experimental.streamlit.utilities import icom as _icom
from pymedphys._streamlit.utilities import config, misc


def main():
    st.title("iCom Logs Explorer")

    site_directories = config.get_site_directories()
    chosen_site = misc.site_picker("Site")
    icom_directory = site_directories[chosen_site]["icom"]
    icom_patients_directory = icom_directory.joinpath("patients")
    st.write(icom_patients_directory)

    selected_paths_by_date = _icom.get_paths_by_date(icom_patients_directory)

    st.write("## Service mode beam utilisation")

    all_relevant_times = _icom.get_relevant_times_for_filepaths(
        selected_paths_by_date["filepath"]
    )
    _icom.plot_all_relevant_times(all_relevant_times)

    st.write("## Select a time to view specific iCom data")

    times = selected_paths_by_date["datetime"].dt.time
    selected_time = st.selectbox("Time", list(times))

    selected_path_by_time = selected_paths_by_date.loc[selected_time == times]

    if len(selected_path_by_time["filepath"]) != 1:
        raise ValueError("Only one filepath per time supported")

    filepath = selected_path_by_time["filepath"].iloc[0]

    st.write(filepath)

    icom_stream = _icom.read_icom_log(filepath)
    icom_data_points = pmp_icom_extract.get_data_points(icom_stream)

    icom_datetime, meterset, machine_id = _icom.get_icom_datetimes_meterset_machine(
        filepath
    )

    icom_time = pd.Series(icom_datetime.dt.time, name="time")
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

    width = _determine_width(raw_delivery_items["mlc"], raw_delivery_items["jaw"])
    length = _determine_length(raw_delivery_items["jaw"])

    icom_dataset = pd.concat(
        [
            icom_time,
            machine_id,
            width,
            length,
            raw_delivery_items,
            turn_table,
            icom_datetime,
        ],
        axis=1,
    )

    st.write(icom_dataset)


def _check_for_consistent_mlc_width_return_mean(weighted_mlc_positions):
    mean = np.mean(weighted_mlc_positions)
    if np.any(np.abs(weighted_mlc_positions - mean) > 1):
        st.write(weighted_mlc_positions)
        raise ValueError("MLCs are not producing a consistent width")

    return mean


def _determine_width(mlc, jaw):
    jaw = np.array(list(jaw))
    mlc = np.array(list(mlc))

    mlc_indices = np.arange(80)
    leaf_centre_pos = np.array((mlc_indices - 39) * 5 - 2.5)  # Not sufficiently tested
    is_mlc_centre_blocked = np.invert(
        (-jaw[:, 0][:, None] <= leaf_centre_pos[None, :])
        & (jaw[:, 1][:, None] >= leaf_centre_pos[None, :])
    )

    mlc[is_mlc_centre_blocked, :] = np.nan
    mean_mlc = np.nanmean(mlc, axis=1)

    absolute_diff = np.abs(mlc - mean_mlc[:, None, :])
    max_absolute_diff = np.nanmax(absolute_diff, axis=1)

    mean_mlc[max_absolute_diff > 0.5] = np.nan
    width = np.sum(mean_mlc, axis=1)

    return pd.Series(width, name="width")


def _determine_length(jaw):
    jaw = np.array(list(jaw))
    length = jaw[:, 0] + jaw[:, 1]

    return pd.Series(length, name="length")
