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

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import scipy
from pymedphys._imports import streamlit as st

from pymedphys._experimental.streamlit.utilities import icom as _icom

from . import _angles, _calculation, _filtering, _frames, _sync, _utilities


def main():
    """The entrance function for the WLutz Arc Streamlit GUI.

    This GUI connects to an iViewDB stored on a shared network drive
    and allows users to plot the difference between the field centre
    and the ball bearing centre accross a range of gantry angles.

    """
    st.title("Winston-Lutz Arc")

    bb_diameter, penumbra = _set_parameters()

    refresh_cache = st.button("Re-query databases")
    (
        database_directory,
        icom_directory,
        wlutz_directory_by_date,
        database_table,
        selected_date,
        selected_machine_id,
    ) = _utilities.get_directories_and_initial_database(refresh_cache)

    icom_patients_directory = icom_directory.joinpath("patients")

    database_table = _get_user_image_set_selection(database_table)
    database_table = _load_image_frame_database(
        database_directory, database_table, refresh_cache
    )

    st.write(
        f"""
            ## Directory where results are being saved

            `{wlutz_directory_by_date}`
        """
    )

    # --

    filepaths_to_load, offset_to_apply = _sync.icom_iview_timestamp_alignment(
        database_table, icom_patients_directory, selected_date, selected_machine_id
    )

    # --

    icom_datasets = []
    for filepath in filepaths_to_load:
        icom_dataframe = _icom.get_icom_dataset(filepath)
        # st.write(icom_dataframe)
        icom_datasets.append(icom_dataframe.copy())

    icom_datasets = pd.concat(icom_datasets, axis=0, ignore_index=True)
    icom_datasets = icom_datasets.sort_values(by="datetime", inplace=False)

    icom_datasets["datetime"] += datetime.timedelta(seconds=offset_to_apply)
    icom_datasets["time"] = icom_datasets["datetime"].dt.round("ms").dt.time

    # icom_datasets.set_index("datetime", inplace=True)

    beam_on_mask = _utilities.expand_border_events(
        np.diff(icom_datasets["meterset"]) > 0
    )
    beam_shade_min = -200 * beam_on_mask
    beam_shade_max = 200 * beam_on_mask

    icom_datasets["beam_shade_min"] = beam_shade_min
    icom_datasets["beam_shade_max"] = beam_shade_max

    beam_on_chart = (
        alt.Chart(icom_datasets)
        .mark_area(fillOpacity=0.1, strokeOpacity=0.3, stroke="black", fill="black")
        .encode(x="datetime:T", y="beam_shade_min:Q", y2="beam_shade_max:Q")
    )

    try:
        icom_datasets = _angles.make_icom_angles_continuous(icom_datasets)
    finally:
        device_angle_chart = (
            beam_on_chart
            + (
                alt.Chart(icom_datasets)
                .transform_fold(
                    ["gantry", "collimator", "turn_table"], as_=["device", "angle"]
                )
                .mark_line(point=True)
                .encode(
                    x="datetime:T",
                    y=alt.Y("angle:Q", axis=alt.Axis(title="Angle (degrees)")),
                    color="device:N",
                    tooltip=["time:N", "device:N", "angle:Q"],
                )
                .properties(title="iCom Angle Parameters")
                .interactive(bind_y=False)
            )
        ).configure_point(size=10)

        st.altair_chart(device_angle_chart, use_container_width=True)

    icom_datasets["width"] = icom_datasets["width"].round(2)

    field_size_chart = (
        alt.Chart(icom_datasets)
        .transform_fold(["length", "width"], as_=["side", "size"])
        .mark_line()
        .encode(
            x="datetime:T",
            y="size:Q",
            color="side:N",
            tooltip=["time:N", "side:N", "size:Q"],
        )
        .properties(title="iCom Field Size")
        .interactive(bind_x=False)
    )
    st.altair_chart(field_size_chart, use_container_width=True)

    st.write(icom_datasets)

    midnight = (
        icom_datasets["datetime"]
        .iloc[0]
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    icom_datasets["seconds_since_midnight"] = (
        icom_datasets["datetime"] - midnight
    ).dt.total_seconds()
    database_table["seconds_since_midnight"] = (
        database_table["datetime"] - midnight
    ).dt.total_seconds()

    for column in ["gantry", "collimator", "turn_table", "width", "length"]:
        _table_transfer_via_interpolation(icom_datasets, database_table, column)

    st.write(database_table)

    # --

    st.write("## Calculations")

    algorithm_options = ["PyMedPhys", "PyLinac"]
    selected_algorithms = st.multiselect(
        "Algorithms to run", algorithm_options, algorithm_options
    )

    database_table["filename"] = database_table["filepath"].apply(
        _utilities.filepath_to_filename
    )
    database_table["time"] = database_table["datetime"].dt.time.apply(str)

    _show_selected_image(
        database_directory, database_table, selected_algorithms, bb_diameter, penumbra
    )

    if st.button("Calculate"):
        _calculation.run_calculation(
            database_table,
            database_directory,
            wlutz_directory_by_date,
            selected_algorithms,
            bb_diameter,
            penumbra,
        )


def _show_selected_image(
    database_directory, database_table, selected_algorithms, bb_diameter, penumbra
):
    show_selected_image = st.checkbox(
        "Select a single image to show results for", False
    )

    filenames = list(database_table["filename"])

    if show_selected_image:
        image_filename = st.selectbox("Select single filepath", filenames)

        st.write(image_filename)
        database_row_all_filename_matches = database_table.loc[
            database_table["filename"] == image_filename
        ]

        relative_image_path = database_row_all_filename_matches["filepath"]
        if len(relative_image_path) != 1:
            raise ValueError("Filepath and filelength should be a one-to-one mapping")

        database_row = database_row_all_filename_matches.iloc[0]
        relative_image_path = database_row["filepath"]

        if _utilities.filepath_to_filename(relative_image_path) != image_filename:
            raise ValueError("Filepath selection did not convert appropriately")

        st.write(relative_image_path)
        results = _calculation.get_results_for_image(
            database_directory,
            relative_image_path,
            selected_algorithms,
            bb_diameter,
            database_row,
            penumbra,
        )

        st.write(results)

        figures = _calculation.plot_diagnostic_figures(
            database_directory,
            relative_image_path,
            bb_diameter,
            database_row,
            penumbra,
            selected_algorithms,
        )

        for fig in figures:
            st.pyplot(fig)


def _set_parameters():
    st.sidebar.write("## Parameters")

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", 8)
    penumbra = st.sidebar.number_input("Penumbra (mm)", 2)

    return bb_diameter, penumbra


def _get_user_image_set_selection(database_table):
    st.write("## Filtering")
    filtered = _filtering.filter_image_sets(database_table)
    filtered.sort_values("datetime", ascending=False, inplace=True)

    st.write(filtered)

    if len(filtered) == 0:
        st.stop()

    return filtered


def _load_image_frame_database(database_directory, input_database_table, refresh_cache):
    st.write("## Loading database image frame data")

    try:
        database_table = _frames.dbf_frame_based_database(
            database_directory, refresh_cache, input_database_table
        )
    except FileNotFoundError:
        database_table = _frames.xml_frame_based_database(
            database_directory, input_database_table
        )

    return database_table


def _table_transfer_via_interpolation(source, location, key):
    interpolation = scipy.interpolate.interp1d(
        source["seconds_since_midnight"], source[key]
    )
    location[key] = interpolation(location["seconds_since_midnight"])
