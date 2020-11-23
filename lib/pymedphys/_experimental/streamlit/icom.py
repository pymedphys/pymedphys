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

import lzma

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

import pymedphys
import pymedphys._icom.delivery as pmp_icom_delivery
import pymedphys._icom.extract as pmp_icom_extract
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

    with lzma.open(filepath, "r") as f:
        icom_stream = f.read()

    icom_data_points = pmp_icom_extract.get_data_points(icom_stream)
    icom_datetime = pd.to_datetime(
        pd.Series([item[8:26].decode() for item in icom_data_points], name="datetime"),
        format="%Y-%m-%d%H:%M:%S",
    )

    icom_time = pd.Series(icom_datetime.dt.time, name="time")
    raw_delivery_items = pd.DataFrame(
        [pmp_icom_delivery.get_delivery_data_items(item) for item in icom_data_points],
        columns=["meterset", "gantry", "collimator", "mlc", "jaw"],
    )

    table = pd.Series(
        [
            pmp_icom_extract.extract(item, "Table Isocentric")[1]
            for item in icom_data_points
        ],
        name="table",
    )

    icom_dataset = pd.concat(
        [icom_time, raw_delivery_items, table, icom_datetime], axis=1
    )

    st.write(icom_dataset)

    delivery = pymedphys.Delivery.from_icom(icom_stream)
    width = _determine_width_from_delivery(delivery)

    length = _determine_length_from_delivery(delivery)
    st.write(f"Width: `{width}` | Length: `{length}`")


def _check_for_consistent_mlc_width_return_mean(weighted_mlc_positions):
    mean = np.mean(weighted_mlc_positions)
    if np.any(np.abs(weighted_mlc_positions - mean) > 1):
        st.write(weighted_mlc_positions)
        raise ValueError("MLCs are not producing a consistent width")

    return mean


def _determine_width_from_delivery(delivery):
    jaw = np.array(delivery.jaw)

    mlc_indices = np.arange(80)
    leaf_centre_pos = np.array((mlc_indices - 39) * 5 - 2.5)  # Not sufficiently tested
    is_mlc_centre_unblocked = (-jaw[:, 0][None, :] <= leaf_centre_pos[:, None]) & (
        jaw[:, 1][None, :] >= leaf_centre_pos[:, None]
    )

    is_mlc_centre_unblocked_for_all_cps = np.all(is_mlc_centre_unblocked, axis=1)

    timestep_meterset_weighting = _get_meterset_timestep_weighting(delivery)

    mlc = np.array(delivery.mlc)
    mlc_a = mlc[:, is_mlc_centre_unblocked_for_all_cps, 0]
    mlc_b = mlc[:, is_mlc_centre_unblocked_for_all_cps, 1]

    side_a = np.sum(mlc_a * timestep_meterset_weighting[:, None], axis=0)
    side_b = np.sum(mlc_b * timestep_meterset_weighting[:, None], axis=0)

    mean_side_a = _check_for_consistent_mlc_width_return_mean(side_a)
    mean_side_b = _check_for_consistent_mlc_width_return_mean(side_b)

    width = mean_side_a + mean_side_b

    return round(width, 1)


def _get_meterset_timestep_weighting(delivery):
    meterset = np.array(delivery.mu)

    diff_meterset = np.concatenate([[0], np.diff(meterset)])
    timestep_meterset_weighting = diff_meterset / meterset[-1]

    if not np.allclose(np.sum(timestep_meterset_weighting), 1):
        raise ValueError("Meterset position weighting should add up to 1")

    return timestep_meterset_weighting


def _determine_length_from_delivery(delivery):
    jaw = np.array(delivery.jaw)
    timestep_meterset_weighting = _get_meterset_timestep_weighting(delivery)

    side_a = np.sum(jaw[:, 0] * timestep_meterset_weighting)
    side_b = np.sum(jaw[:, 1] * timestep_meterset_weighting)

    length = side_a + side_b

    return round(length, 1)
