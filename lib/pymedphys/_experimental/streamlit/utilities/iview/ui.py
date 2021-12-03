# Copyright (C) 2021 Cancer Care Associates
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

import pathlib
from typing import List, Union, cast

from typing_extensions import Literal

Number = Union[float, int]
import datetime

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import scipy
from pymedphys._imports import streamlit as st

from pymedphys._experimental.streamlit.utilities import icom as _icom
from pymedphys._experimental.streamlit.utilities import iteration as _iteration

from . import _angles, _filtering, _frames, _sync, _utilities

MAXIMUM_ANGLE_AXIS_MAGNITUDE = 200


def iview_and_icom_filter_and_align(
    config, advanced_mode, filter_angles_by_default=False, quiet=False
):
    if quiet:
        refresh_cache = True
    else:
        refresh_cache = st.button("Re-query databases")
    (
        database_directory,
        icom_directory,
        database_table,
        selected_date,
        linac_to_directories_map,
    ) = _utilities.get_directories_and_initial_database(config, refresh_cache)

    icom_patients_directory = icom_directory.joinpath("patients")

    if not quiet:
        st.write("## Filtering")

    database_table = get_user_image_set_selection(
        database_table, advanced_mode, quiet=quiet
    )
    database_table = load_image_frame_database(
        database_directory, database_table, refresh_cache, advanced_mode
    )

    machine_ids = database_table["machine_id"].unique()
    if len(machine_ids) != 1:
        raise ValueError("Expected exactly one machine id")

    selected_machine_id = machine_ids[0]
    qa_directory = pathlib.Path(linac_to_directories_map[selected_machine_id]["qa"])

    filepaths_to_load, offset_to_apply = _sync.icom_iview_timestamp_alignment(
        database_table,
        icom_patients_directory,
        selected_date,
        selected_machine_id,
        advanced_mode,
        quiet=quiet,
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
        icom_datasets = _angles.make_icom_angles_continuous(icom_datasets, quiet=quiet)
    finally:
        if advanced_mode:
            beam_on_mask = _utilities.expand_border_events(
                np.diff(icom_datasets["meterset"]) > 0
            )
            beam_shade_min = -MAXIMUM_ANGLE_AXIS_MAGNITUDE * beam_on_mask
            beam_shade_max = MAXIMUM_ANGLE_AXIS_MAGNITUDE * beam_on_mask

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

    for lower, upper, centre, diameter in (
        ("x_lower", "x_upper", "centre_x", "width"),
        ("y_lower", "y_upper", "centre_y", "length"),
    ):
        (
            icom_datasets[lower],
            icom_datasets[upper],
        ) = get_bounds_from_centre_and_diameter(
            icom_datasets[centre], icom_datasets[diameter]
        )

    for column in [
        "gantry",
        "collimator",
        "turn_table",
        "x_lower",
        "x_upper",
        "y_lower",
        "y_upper",
    ]:
        table_transfer_via_interpolation(icom_datasets, database_table, column)

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

    if not quiet:
        st.write("## Filtering by gantry and collimator")
        if st.checkbox(
            "Filter to specific gantry and collimator angles",
            value=filter_angles_by_default,
        ):
            database_table = _angle_filtering(database_table, advanced_mode)

    return database_table, database_directory, qa_directory, selected_date


def get_bounds_from_centre_and_diameter(centre, diameter):
    """Convert centre and field size into collimation edge positions."""
    lower = centre - diameter / 2
    upper = centre + diameter / 2

    return lower, upper


def get_user_image_set_selection(database_table, advanced_mode, quiet=False):
    """Narrow down the database_table via a range of user inputs

    User inputs are detailed further within the docstring of
    ``_filtering.filter_image_sets``.
    """
    filtered = _filtering.filter_image_sets(database_table, advanced_mode, quiet=quiet)
    filtered.sort_values("datetime", ascending=False, inplace=True)

    if advanced_mode:
        st.write(filtered)

    if len(filtered) == 0:
        st.stop()

    return filtered


def load_image_frame_database(
    database_directory, input_database_table, refresh_cache, advanced_mode
):
    """Load an image frame, attempting both known iView database schemas"""
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


def table_transfer_via_interpolation(source, location, key):
    """Create a linear interpolation function for a given dataframe
    column based on the iCom timestamps.

    This is utilised to then interpolate the data points to the iView
    frames.
    """
    interpolation = scipy.interpolate.interp1d(
        source["seconds_since_midnight"], source[key]
    )
    location[key] = interpolation(location["seconds_since_midnight"])


def _angle_filtering(
    database_table: "pd.DataFrame", advanced_mode: bool
) -> "pd.DataFrame":

    st.write(
        """
        ### Angle filtering definitions

        Select between `-180` degrees and `+180` degrees. Write the
        angles you wish to select below separated by a comma (`,`).
        """
    )

    gantry_column, collimator_column = st.beta_columns(2)

    default_gantry_angles: List[Number] = [-180, -135, -90, -45, 0, 45, 90, 135, 180]
    default_collimator_angles: List[Number] = [-180, -90, 0, 90, 180]

    angles = {}
    for name, tolerance, column, default_angles in [
        ("gantry", 10, gantry_column, default_gantry_angles),
        ("collimator", 5, collimator_column, default_collimator_angles),
    ]:
        with column:
            name = cast(Literal["gantry", "collimator"], name)
            angles[name] = _user_selected_angles(
                name, default_angles, tolerance, advanced_mode
            )

    selected_gantry_angles = angles["gantry"][0]
    gantry_angle_tolerance = angles["gantry"][1]

    selected_collimator_angles = angles["collimator"][0]
    collimator_angle_tolerance = angles["collimator"][1]

    def _treatment_callback(_dataframe, _data, treatment: str):
        if advanced_mode:
            st.write(f"#### {treatment}")

    def _port_callback(
        dataframe: pd.DataFrame,
        collated_dataframes: List[pd.DataFrame],
        _treatment,
        port: str,
    ):
        dataframes: List[pd.DataFrame] = []

        for gantry_angle in selected_gantry_angles:
            for collimator_angle in selected_collimator_angles:
                mask = (
                    (dataframe["gantry"] >= gantry_angle - gantry_angle_tolerance)
                    & (dataframe["gantry"] <= gantry_angle + gantry_angle_tolerance)
                    & (
                        dataframe["collimator"]
                        >= collimator_angle - collimator_angle_tolerance
                    )
                    & (
                        dataframe["collimator"]
                        <= collimator_angle + collimator_angle_tolerance
                    )
                )
                masked = dataframe[mask]
                if len(masked) == 0:
                    continue

                closest_gantry_angle_index = np.argmin(
                    np.abs(masked["gantry"] - gantry_angle)
                )
                dataframes.append(masked.iloc[[closest_gantry_angle_index]])

        if len(dataframes) == 0:
            return

        concatenated_dataframes = pd.concat(dataframes, axis=0)

        if advanced_mode:
            st.write(f"##### {port}")
            st.write(concatenated_dataframes[["gantry", "collimator"]])

        collated_dataframes.append(concatenated_dataframes)

    if advanced_mode:
        st.write(
            """
            ### Gantry and collimator angles selected per treatment and port
            """
        )

    collated_dataframes: List[pd.DataFrame] = []

    _iteration.iterate_over_columns(
        database_table,
        data=collated_dataframes,
        columns=["treatment", "port"],
        callbacks=[_treatment_callback, _port_callback],
    )

    if len(collated_dataframes) == 0:
        st.error("No DataFrames match the provided filters")
        st.stop()

    database_table = pd.concat(collated_dataframes, axis=0)

    return database_table


def _user_selected_angles(
    name: Literal["gantry", "collimator"],
    default_selection: List[Number],
    default_tolerance: Number,
    advanced_mode,
):
    capitalised_name = name.capitalize()
    text_box_default = ", ".join(np.array(default_selection).astype(str))

    st.write(f"#### {capitalised_name} filtering")

    angles = st.text_input(f"{capitalised_name} angles", text_box_default)
    angles = np.array(angles.split(",")).astype(float).tolist()
    if advanced_mode:
        st.write(f"`{angles}`")

    tolerance = st.number_input(
        f"{capitalised_name} angle tolerance", 0, None, default_tolerance
    )

    return angles, tolerance
