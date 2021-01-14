# Copyright (C) 2020 Cancer Care Associates and Simon Biggs

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
from pymedphys._imports import natsort
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt, scipy
from pymedphys._imports import streamlit as st
from pymedphys._imports import streamlit_ace, tomlkit

from pymedphys._experimental.streamlit.utilities import icom as _icom

from . import (
    _angles,
    _calculation,
    _config,
    _corrections,
    _excel,
    _filtering,
    _frames,
    _sync,
    _utilities,
)


def main():
    """The entrance function for the WLutz Arc Streamlit GUI.

    This GUI connects to an iViewDB stored on a shared network drive
    and allows users to plot the difference between the field centre
    and the ball bearing centre accross a range of gantry angles.

    """
    bb_diameter, penumbra, advanced_mode, demo_mode = _set_parameters()
    config = _config.get_config(demo_mode)

    if demo_mode and advanced_mode:
        st.write("## Demo Configuration")
        config = tomlkit.loads(
            streamlit_ace.st_ace(value=tomlkit.dumps(config), language="toml")
        )

    refresh_cache = st.button("Re-query databases")
    (
        database_directory,
        icom_directory,
        wlutz_directory_by_date,
        database_table,
        selected_date,
        selected_machine_id,
    ) = _utilities.get_directories_and_initial_database(config, refresh_cache)

    icom_patients_directory = icom_directory.joinpath("patients")

    database_table = _get_user_image_set_selection(database_table, advanced_mode)
    database_table = _load_image_frame_database(
        database_directory, database_table, refresh_cache, advanced_mode
    )

    if advanced_mode:
        st.write(
            f"""
                ## Directory where results are being saved

                `{wlutz_directory_by_date}`
            """
        )

    filepaths_to_load, offset_to_apply = _sync.icom_iview_timestamp_alignment(
        database_table,
        icom_patients_directory,
        selected_date,
        selected_machine_id,
        advanced_mode,
    )

    icom_datasets = []
    for filepath in filepaths_to_load:
        icom_dataframe = _icom.get_icom_dataset(filepath)
        icom_datasets.append(icom_dataframe.copy())

    icom_datasets = pd.concat(icom_datasets, axis=0, ignore_index=True)
    icom_datasets = icom_datasets.sort_values(by="datetime", inplace=False)

    icom_datasets["datetime"] = icom_datasets["datetime"] + datetime.timedelta(
        seconds=offset_to_apply
    )
    icom_datasets["time"] = icom_datasets["datetime"].dt.round("ms").dt.time

    try:
        icom_datasets = _angles.make_icom_angles_continuous(icom_datasets)
    finally:
        if advanced_mode:
            beam_on_mask = _utilities.expand_border_events(
                np.diff(icom_datasets["meterset"]) > 0
            )
            beam_shade_min = -200 * beam_on_mask
            beam_shade_max = 200 * beam_on_mask

            icom_datasets["beam_shade_min"] = beam_shade_min
            icom_datasets["beam_shade_max"] = beam_shade_max

            beam_on_chart = (
                alt.Chart(icom_datasets)
                .mark_area(
                    fillOpacity=0.1, strokeOpacity=0.3, stroke="black", fill="black"
                )
                .encode(x="datetime:T", y="beam_shade_min:Q", y2="beam_shade_max:Q")
            )

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

    if advanced_mode:
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

    icom_datasets["x_lower"] = icom_datasets["centre_x"] - icom_datasets["width"] / 2
    icom_datasets["x_upper"] = icom_datasets["centre_x"] + icom_datasets["width"] / 2
    icom_datasets["y_lower"] = icom_datasets["centre_y"] - icom_datasets["length"] / 2
    icom_datasets["y_upper"] = icom_datasets["centre_y"] + icom_datasets["length"] / 2

    for column in [
        "gantry",
        "collimator",
        "turn_table",
        "x_lower",
        "x_upper",
        "y_lower",
        "y_upper",
    ]:
        _table_transfer_via_interpolation(icom_datasets, database_table, column)

    icom_seconds = icom_datasets["seconds_since_midnight"]
    iview_seconds = database_table["seconds_since_midnight"]

    alignment_indices = np.argmin(
        np.abs(icom_seconds.values[None, :] - iview_seconds.values[:, None]), axis=1
    )

    energies = icom_datasets["energy"].values[alignment_indices]
    database_table["energy"] = energies

    database_table["width"] = database_table["x_upper"] - database_table["x_lower"]
    database_table["length"] = database_table["y_upper"] - database_table["y_lower"]

    if advanced_mode:
        st.write(database_table)

    _calculation.calculations_ui(
        database_table,
        database_directory,
        wlutz_directory_by_date,
        bb_diameter,
        penumbra,
        advanced_mode,
    )

    _presentation_of_results(wlutz_directory_by_date, advanced_mode)


def _presentation_of_results(wlutz_directory_by_date, advanced_mode):
    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")

    try:
        calculated_results = pd.read_csv(raw_results_csv_path, index_col=False)
    except FileNotFoundError:
        return

    st.write("## Overview of Results")

    dataframe = calculated_results.sort_values("seconds_since_midnight")
    dataframe_by_algorithm = _utilities.filter_by(dataframe, "algorithm", "PyMedPhys")

    statistics = _overview_statistics(dataframe_by_algorithm)
    st.write(statistics)

    _overview_figures(dataframe_by_algorithm)

    wlutz_xlsx_filepath = wlutz_directory_by_date.joinpath("overview.xlsx")
    _excel.write_excel_overview(dataframe, statistics, wlutz_xlsx_filepath)

    if advanced_mode:
        st.write("### Experimental iCom and collimator corrections")

        experimental_collimator_corrections = st.checkbox(
            "Turn on experimental collimator and iCom correction statistics?"
        )
        if experimental_collimator_corrections:
            st.write("#### Statistics")

            (
                dataframe_with_corrections,
                collimator_correction,
            ) = _corrections.apply_corrections(dataframe_by_algorithm)

            dataframe_with_corrections["diff_x"] = dataframe_with_corrections[
                "diff_x_coll_corrected"
            ]
            dataframe_with_corrections["diff_y"] = dataframe_with_corrections[
                "diff_y_coll_corrected"
            ]

            statistics_with_corrections = _overview_statistics(
                dataframe_with_corrections
            )
            st.write(statistics_with_corrections)

            st.write("#### Predicted Collimator Rotation Correction")
            st.write(
                f"""
                    * Shift in MLC travel direction =
                    `{round(collimator_correction[0], 2)}` mm
                    * Shift in Jaw travel direction =
                    `{round(collimator_correction[1], 2)}` mm
                """
            )


def _overview_figures(dataframe):
    energies = natsort.natsorted(dataframe["energy"].unique())

    for energy in energies:
        st.write(f"### {energy}")
        dataframe_by_energy = _utilities.filter_by(dataframe, "energy", energy)
        treatments = natsort.natsorted(dataframe["treatment"].unique())

        for treatment in treatments:
            dataframe_by_energy_treatment = _utilities.filter_by(
                dataframe_by_energy, "treatment", treatment
            )

            if len(dataframe_by_energy_treatment) == 0:
                continue

            st.write(f"#### {treatment}")

            for title, column, axis in [
                ("Radial", "diff_y", "y-axis"),
                ("Transverse", "diff_x", "x-axis"),
            ]:
                altair_chart = (
                    alt.Chart(dataframe_by_energy_treatment)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("gantry", axis=alt.Axis(title="Gantry")),
                        y=alt.Y(
                            column,
                            axis=alt.Axis(title=f"iView {axis} (mm) [Field - BB]"),
                        ),
                        color=alt.Color("port", legend=alt.Legend(title="Port")),
                        tooltip=[
                            "time",
                            "port",
                            "diff_x",
                            "diff_y",
                            "gantry",
                            "collimator",
                            "turn_table",
                            "filename",
                        ],
                    )
                ).properties(title=f"{title} | {energy} | {treatment}")

                st.altair_chart(altair_chart, use_container_width=True)
                st.write(
                    _overview_statistics(
                        dataframe_by_energy_treatment, directions=(column,)
                    )
                )

    # dataframe_by_algorithm = _utilities.filter_by(dataframe, "algorithm", "PyMedPhys")

    st.write(
        """
            `TODO:`
            * Use the data collected on the `2020-12-17` as the reference
            * Create figures here organised first by energy, then by treatment,
              then direction.
              * These figures will collate all ports for a given setup
                onto one plot
              * Only include PyMedPhys results for these.
            * Beneath each figure write out the statistics for that
              figure.
            * Write those created figures to the Excel overview.
        """
    )


def _overview_statistics(dataframe, directions=("diff_y", "diff_x")):
    statistics = []
    energies = dataframe["energy"].unique()
    energies = natsort.natsorted(energies)

    column_direction_map = {"diff_x": "Transverse", "diff_y": "Radial"}
    for energy in energies:
        dataframe_by_energy = _utilities.filter_by(dataframe, "energy", energy)

        for column in directions:
            statistics.append(
                {
                    "energy": energy,
                    "direction": column_direction_map[column],
                    "min": np.nanmin(dataframe_by_energy[column]),
                    "max": np.nanmax(dataframe_by_energy[column]),
                    "mean": np.nanmean(dataframe_by_energy[column]),
                    "median": np.nanmedian(dataframe_by_energy[column]),
                }
            )

    statistics = pd.DataFrame.from_dict(statistics).round(2)
    return statistics


def _set_parameters():
    st.sidebar.write("# Configuration")

    try:
        _config.get_config(False)
        demo_mode = st.sidebar.checkbox("Demo Mode", value=False)
    except FileNotFoundError:
        demo_mode = True

    advanced_mode = st.sidebar.checkbox("Advanced Mode", value=False)

    st.sidebar.write("# Parameters")

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", 8)
    penumbra = st.sidebar.number_input("Penumbra (mm)", 2)

    return bb_diameter, penumbra, advanced_mode, demo_mode


def _get_user_image_set_selection(database_table, advanced_mode):
    st.write("## Filtering")
    filtered = _filtering.filter_image_sets(database_table, advanced_mode)
    filtered.sort_values("datetime", ascending=False, inplace=True)

    if advanced_mode:
        st.write(filtered)

    if len(filtered) == 0:
        st.stop()

    return filtered


def _load_image_frame_database(
    database_directory, input_database_table, refresh_cache, advanced_mode
):
    if advanced_mode:
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
