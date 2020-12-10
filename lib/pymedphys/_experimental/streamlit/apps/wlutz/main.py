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


import base64
import datetime

from pymedphys._imports import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt, pylinac, scipy
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._utilities import transforms as pmp_transforms
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api
from pymedphys._wlutz import reporting

from pymedphys._experimental.streamlit.utilities import icom as _icom

from . import _altair, _dbf, _filtering, _frames, _utilities

GANTRY_EXPECTED_SPEED_LIMIT = 1  # RPM
COLLIMATOR_EXPECTED_SPEED_LIMIT = 2.7  # RPM
NOISE_BUFFER_FACTOR = 5  # To allow a noisy point to not trigger the speed limit


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

    st.write("## iView to iCom timestamp alignment")

    selected_paths_by_date = _icom.get_paths_by_date(
        icom_patients_directory, selected_date=selected_date
    )

    all_relevant_times = _icom.get_relevant_times_for_filepaths(
        selected_paths_by_date["filepath"]
    )

    relevant_times = all_relevant_times[selected_machine_id]

    min_iview_datetime = (np.min(database_table["datetime"])).floor("min")
    max_iview_datetime = (np.max(database_table["datetime"])).ceil("min")

    time_step = datetime.timedelta(minutes=1)
    min_icom_datetime = (np.min(relevant_times["datetime"])).floor("min")
    max_icom_datetime = (np.max(relevant_times["datetime"])).ceil("min")

    buffer = datetime.timedelta(minutes=30)
    init_min_time = np.max([min_iview_datetime - buffer, min_icom_datetime])
    init_max_time = np.min([max_iview_datetime + buffer, max_icom_datetime])

    initial_region = [init_min_time.time(), init_max_time.time()]

    icom_time_range = st.slider(
        "iCom alignment range",
        min_value=min_icom_datetime.time(),
        max_value=max_icom_datetime.time(),
        step=time_step,
        value=initial_region,
    )

    time = relevant_times["datetime"].dt.time
    icom_lookup_mask = (time >= icom_time_range[0]) & (time <= icom_time_range[1])
    time_filtered_icom_times = relevant_times.loc[icom_lookup_mask]

    _icom.plot_relevant_times(
        time_filtered_icom_times,
        step=1,
        title="iCom | Timesteps with recorded meterset",
    )

    _icom.plot_relevant_times(
        database_table, step=1, title="iView | Timesteps with recorded image frames"
    )

    iview_datetimes = pd.Series(database_table["datetime"], name="datetime")

    icom_datetimes = pd.Series(time_filtered_icom_times["datetime"], name="datetime")

    loop_offset, loop_minimise_f = _determine_loop_offset(
        iview_datetimes, icom_datetimes
    )
    basinhopping_offset, basinhopping_minimise_f = _determine_basinhopping_offset(
        iview_datetimes, icom_datetimes
    )

    if loop_minimise_f > basinhopping_minimise_f:
        offset_to_apply = basinhopping_offset
        offset_used = "basinhopping"
    else:
        offset_to_apply = loop_offset
        offset_used = "loop"

    st.write(
        f"""
            Offset estimation undergone with two approaches. The offset
            from the `{offset_used}` approach was utilised. The offset
            required to align the iCom timestamps to the iView
            timestamps was determined to be
            `{round(offset_to_apply, 1)}` s.

            * Basinhopping offset: `{round(basinhopping_offset, 2)}`
              * Minimiser `{round(basinhopping_minimise_f, 4)}`
            * Loop offset: `{round(loop_offset, 2)}`
              * Minimiser `{round(loop_minimise_f, 4)}`
        """
    )

    if np.abs(basinhopping_offset - loop_offset) > 1:
        st.error(
            "The time offset methods disagree by more than 1 second. "
            "Offset alignment accuracy can be improved by either "
            "decreasing the time of capture between consecutive imaging "
            "frames (such as provided "
            "by movie mode) or by adjusting the clocks on both the "
            "iView and the NRT so that the expected deviation between "
            "them is less than the time between consecutive images."
        )

    usable_icom_times = relevant_times.copy()
    usable_icom_times["datetime"] += datetime.timedelta(seconds=offset_to_apply)

    time = usable_icom_times["datetime"].dt.time
    adjusted_buffer = datetime.timedelta(seconds=30)
    adjusted_icom_lookup_mask = (
        time >= (min_iview_datetime - adjusted_buffer).time()
    ) & (time <= (max_iview_datetime + adjusted_buffer).time())
    usable_icom_times = usable_icom_times.loc[adjusted_icom_lookup_mask]

    _icom.plot_relevant_times(
        usable_icom_times, step=1, title=f"iCom | With {offset_used} offset applied"
    )

    time_diffs = _get_time_diffs(iview_datetimes, usable_icom_times["datetime"])
    time_diffs = pd.concat([iview_datetimes, time_diffs], axis=1)
    time_diffs["time"] = time_diffs["datetime"].dt.time

    raw_chart = (
        alt.Chart(time_diffs)
        .mark_circle()
        .encode(
            x=alt.X("datetime", axis=alt.Axis(title="iView timestamp")),
            y=alt.Y(
                "time_diff",
                axis=alt.Axis(title="Time diff [iView - Adjusted iCom] (s)"),
            ),
            tooltip=["time:N", "time_diff"],
        )
    ).properties(
        title="Time displacement between iView image timestamp and closest iCom record"
    )

    st.altair_chart(altair_chart=raw_chart, use_container_width=True)

    max_diff = np.max(np.abs(time_diffs["time_diff"]))

    st.write(
        "The maximum deviation between an iView frame and the closest "
        f"adjusted iCom timestep was found to be "
        f"`{round(max_diff, 1)}` s."
    )

    # --

    filepaths_to_load = usable_icom_times["filepath"].unique()

    icom_datasets = []
    for filepath in filepaths_to_load:
        icom_dataframe = _icom.get_icom_dataset(filepath)
        st.write(icom_dataframe)
        icom_datasets.append(icom_dataframe.copy())

    icom_datasets = pd.concat(icom_datasets, axis=0, ignore_index=True)
    icom_datasets = icom_datasets.sort_values(by="datetime", inplace=False)

    icom_datasets["datetime"] += datetime.timedelta(seconds=offset_to_apply)
    icom_datasets["time"] = icom_datasets["datetime"].dt.round("ms").dt.time

    # icom_datasets.set_index("datetime", inplace=True)

    beam_on_mask = expand_border_events(np.diff(icom_datasets["meterset"]) > 0)
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
        angle_speed_check(icom_datasets)
    except ValueError:
        icom_datasets["gantry"] = attempt_to_make_angle_continuous(
            icom_datasets["datetime"],
            icom_datasets["gantry"].to_numpy(),
            GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
        )
        icom_datasets["collimator"] = attempt_to_make_angle_continuous(
            icom_datasets["datetime"],
            icom_datasets["collimator"].to_numpy(),
            COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR,
        )

    icom_datasets["width"] = icom_datasets["width"].round(2)

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

    angle_speed_check(icom_datasets)

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
        raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")
        try:
            previously_calculated_results = pd.read_csv(
                raw_results_csv_path, index_col=False
            )
        except FileNotFoundError:
            previously_calculated_results = None

        st.sidebar.write("---\n## Progress")
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()

        collated_results = pd.DataFrame()
        chart_bucket = {}

        total_files = len(database_table["filepath"])

        for i, relative_image_path in enumerate(database_table["filepath"][::-1]):
            if previously_calculated_results is not None:
                results = previously_calculated_results.loc[
                    previously_calculated_results["filepath"] == relative_image_path
                ][RESULTS_DATA_COLUMNS]

                selected_algorithms_already_calculated = set(
                    selected_algorithms
                ).issubset(results["algorithm"].unique())

            if (
                previously_calculated_results is None
                or not selected_algorithms_already_calculated
            ):
                row = database_table.iloc[i]
                edge_lengths = [row["width"], row["length"]]
                # field_rotation = 90 - row["collimator"]

                results = _get_results_for_image(
                    database_directory,
                    relative_image_path,
                    selected_algorithms,
                    bb_diameter,
                    edge_lengths,
                    penumbra,
                )

            collated_results = collated_results.append(results)

            working_table = results.merge(
                database_table, left_on="filepath", right_on="filepath"
            )

            working_table["transformed_field_rotation"] = (
                90 - working_table["field_rotation"] % 90
            )
            working_table["transformed_collimator"] = working_table["collimator"] % 90

            treatment = _collapse_column_to_single_value(working_table, "treatment")
            port = _collapse_column_to_single_value(working_table, "port")

            try:
                treatment_chart_bucket = chart_bucket[treatment]
            except KeyError:
                chart_bucket[treatment] = {}
                treatment_chart_bucket = chart_bucket[treatment]

            table_filtered_by_treatment = working_table.loc[
                working_table["treatment"] == treatment
            ]

            table_filtered_by_port = table_filtered_by_treatment.loc[
                table_filtered_by_treatment["port"] == port
            ]
            try:
                for _, item in treatment_chart_bucket[port].items():
                    item.add_rows(table_filtered_by_port)
            except KeyError:
                st.write(f"### Treatment: `{treatment}` | Port: `{port}`")
                port_chart_bucket = _altair.build_both_axis_altair_charts(
                    table_filtered_by_port
                )
                treatment_chart_bucket[port] = port_chart_bucket

            ratio_complete = (i + 1) / total_files
            progress_bar.progress(ratio_complete)

            percent_complete = round(ratio_complete * 100, 2)
            status_text.text(f"{percent_complete}% Complete")

        contextualised_results: pd.DataFrame = collated_results.merge(
            database_table, left_on="filepath", right_on="filepath"
        )

        st.write("## Raw results")
        st.write(contextualised_results)

        wlutz_directory_by_date.mkdir(parents=True, exist_ok=True)

        merged_with_previous = pd.concat(
            [contextualised_results, previously_calculated_results]
        )
        merged_with_previous.drop_duplicates(inplace=True)
        merged_with_previous.to_csv(raw_results_csv_path, index=False)

        statistics_collection = []

        for treatment, treatment_chart_bucket in chart_bucket.items():
            for port, port_chart_bucket in treatment_chart_bucket.items():
                for column, orientation in zip(
                    ["diff_x", "diff_y"], ["Transverse", "Radial"]
                ):
                    plot_filename = f"{treatment}-{port}-{orientation}.png"
                    plot_filepath = wlutz_directory_by_date.joinpath(plot_filename)

                    mask = (contextualised_results["treatment"] == treatment) & (
                        contextualised_results["port"] == port
                    )

                    masked = contextualised_results.loc[mask]

                    fig, ax = plt.subplots()
                    for algorithm in sorted(selected_algorithms):
                        algorithm_masked = masked.loc[masked["algorithm"] == algorithm]
                        ax.plot(
                            algorithm_masked["gantry"],
                            algorithm_masked[column],
                            ".-",
                            label=algorithm,
                        )

                        description = algorithm_masked[column].describe()
                        description = description.round(2)
                        description["algorithm"] = algorithm
                        description["treatment"] = treatment
                        description["port"] = port
                        description["orientation"] = orientation

                        statistics_collection.append(description)

                    ax.set_xlabel("Gantry Angle (degrees)")
                    ax.set_ylabel("Field centre - BB centre (mm)")

                    descriptor = f"{treatment} | {port} | {orientation}"
                    ax.set_title(descriptor)
                    ax.grid("true")

                    ax.legend(loc="best")
                    fig.savefig(plot_filepath)

        st.write("## Overview Statistics")

        statistics_collection = pd.concat(statistics_collection, axis=1).T
        statistics_collection.reset_index(inplace=True)
        statistics_collection = statistics_collection[
            ["treatment", "port", "orientation", "algorithm", "min", "max", "mean"]
        ]

        st.write(statistics_collection)

        statistics_filename = "statistics_overview.csv"

        statistics_overview_csv_path = wlutz_directory_by_date.joinpath(
            statistics_filename
        )
        statistics_collection.to_csv(statistics_overview_csv_path, index=False)

        with open(statistics_overview_csv_path, "rb") as f:
            csv_bytes = f.read()

        b64 = base64.b64encode(csv_bytes).decode()
        href = f"""
            <a href=\"data:file/zip;base64,{b64}\" download='{statistics_filename}'>
                Download `statistics_overview.csv`.
            </a>
        """
        st.markdown(href, unsafe_allow_html=True)


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
        row = database_table.loc[database_table["filename"] == image_filename]

        relative_image_path = row["filepath"]
        if len(relative_image_path) != 1:
            raise ValueError("Filepath and filelength should be a one-to-one mapping")

        relative_image_path = relative_image_path.iloc[0]

        if _utilities.filepath_to_filename(relative_image_path) != image_filename:
            raise ValueError("Filepath selection did not convert appropriately")

        st.write(relative_image_path)

        edge_lengths = [row["width"].iloc[0], row["length"].iloc[0]]
        # field_rotation = 90 - row["collimator"].iloc[0]

        results = _get_results_for_image(
            database_directory,
            relative_image_path,
            selected_algorithms,
            bb_diameter,
            edge_lengths,
            penumbra,
        )

        st.write(results)

        figures = _plot_diagnostic_figures(
            database_directory,
            relative_image_path,
            bb_diameter,
            edge_lengths,
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


def _plot_diagnostic_figures(
    database_directory,
    relative_image_path,
    bb_diameter,
    edge_lengths,
    penumbra,
    selected_algorithms,
):
    full_image_path = _get_full_image_path(database_directory, relative_image_path)
    wlutz_input_parameters = _get_wlutz_input_parameters(
        full_image_path, bb_diameter, edge_lengths, penumbra
    )

    figures = []

    for algorithm in selected_algorithms:
        field_centre, _, bb_centre = _calculate_wlutz(
            full_image_path, algorithm, bb_diameter, edge_lengths, penumbra
        )

        fig, axs = _create_figure(field_centre, bb_centre, wlutz_input_parameters)
        axs[0, 0].set_title(algorithm)
        figures.append(fig)

    return figures


def _get_full_image_path(database_directory, relative_image_path):
    return database_directory.joinpath(relative_image_path)


RESULTS_DATA_COLUMNS = [
    "filepath",
    "algorithm",
    "diff_x",
    "diff_y",
    "field_centre_x",
    "field_centre_y",
    "field_rotation",
    "bb_centre_x",
    "bb_centre_y",
]


def _get_results_for_image(
    database_directory,
    relative_image_path,
    selected_algorithms,
    bb_diameter,
    edge_lengths,
    penumbra,
):
    full_image_path = _get_full_image_path(database_directory, relative_image_path)

    results_data = []

    for algorithm in selected_algorithms:

        field_centre, field_rotation_calculated, bb_centre = _calculate_wlutz(
            full_image_path, algorithm, bb_diameter, edge_lengths, penumbra
        )
        results_data.append(
            {
                "filepath": relative_image_path,
                "algorithm": algorithm,
                "diff_x": field_centre[0] - bb_centre[0],
                "diff_y": field_centre[1] - bb_centre[1],
                "field_centre_x": field_centre[0],
                "field_centre_y": field_centre[1],
                "field_rotation": field_rotation_calculated,
                "bb_centre_x": bb_centre[0],
                "bb_centre_y": bb_centre[1],
            }
        )

    results = pd.DataFrame.from_dict(results_data)

    if set(results.columns) != set(RESULTS_DATA_COLUMNS):
        raise ValueError("Unexpected columns")

    return results


def _get_wlutz_input_parameters(image_path, bb_diameter, edge_lengths, penumbra):
    field_parameters = _get_field_parameters(image_path, edge_lengths, penumbra)
    wlutz_input_parameters = {
        "bb_diameter": bb_diameter,
        "edge_lengths": edge_lengths,
        "penumbra": penumbra,
        **field_parameters,
    }

    return wlutz_input_parameters


def _create_figure(field_centre, bb_centre, wlutz_input_parameters):
    fig, axs = reporting.image_analysis_figure(
        wlutz_input_parameters["x"],
        wlutz_input_parameters["y"],
        wlutz_input_parameters["image"],
        bb_centre,
        field_centre,
        wlutz_input_parameters["field_rotation"],
        wlutz_input_parameters["bb_diameter"],
        wlutz_input_parameters["edge_lengths"],
        wlutz_input_parameters["penumbra"],
    )

    return fig, axs


@st.cache(show_spinner=False)
def _calculate_wlutz(image_path, algorithm, bb_diameter, edge_lengths, penumbra):
    wlutz_input_parameters = _get_wlutz_input_parameters(
        image_path, bb_diameter, edge_lengths, penumbra
    )

    if wlutz_input_parameters["field_rotation"] == np.nan:
        field_centre = [np.nan, np.nan]
        field_rotation = np.nan
        bb_centre = [np.nan, np.nan]
    else:
        calculate_function = ALGORITHM_FUNCTION_MAP[algorithm]
        field_centre, field_rotation, bb_centre = calculate_function(
            **wlutz_input_parameters
        )

    return field_centre, field_rotation, bb_centre


def _pymedphys_wlutz_calculate(
    field,
    bb_diameter,
    edge_lengths,
    penumbra,
    pymedphys_field_centre,
    field_rotation,
    **_,
):
    field_centre = pymedphys_field_centre

    try:
        bb_centre = findbb.optimise_bb_centre(
            field,
            bb_diameter,
            edge_lengths,
            penumbra,
            field_centre,
            field_rotation,
            pylinac_tol=None,
        )
    except ValueError:
        bb_centre = [np.nan, np.nan]

    return field_centre, field_rotation, bb_centre


def _pylinac_wlutz_calculate(
    field, edge_lengths, penumbra, pymedphys_field_centre, field_rotation, **_
):
    version_to_use = pylinac.__version__

    try:
        pylinac_results = pmp_pylinac_api.run_wlutz(
            field,
            edge_lengths,
            penumbra,
            pymedphys_field_centre,
            field_rotation,
            find_bb=True,
            interpolated_pixel_size=0.05,
            pylinac_versions=[version_to_use],
            fill_errors_with_nan=True,
        )

        field_centre = pylinac_results[version_to_use]["field_centre"]
        bb_centre = pylinac_results[version_to_use]["bb_centre"]

    except ValueError:
        field_centre = [np.nan, np.nan]
        bb_centre = [np.nan, np.nan]

    return field_centre, field_rotation, bb_centre


ALGORITHM_FUNCTION_MAP = {
    "PyMedPhys": _pymedphys_wlutz_calculate,
    "PyLinac": _pylinac_wlutz_calculate,
}


@st.cache(show_spinner=False)
def _get_pymedphys_field_centre_and_rotation(image_path, edge_lengths, penumbra):
    x, y, image, field = _load_image_field_interpolator(image_path)
    initial_centre = findfield.get_centre_of_mass(x, y, image)

    try:
        field_centre, field_rotation = findfield.field_centre_and_rotation_refining(
            field, edge_lengths, penumbra, initial_centre, pylinac_tol=None
        )
    except ValueError:
        field_centre = [np.nan, np.nan]
        field_rotation = np.nan

    return field_centre, field_rotation


def _load_image_field_interpolator(image_path):
    raw_image = lljpeg.imread(image_path)
    x, y, image = iview.iview_image_transform(raw_image)
    field = imginterp.create_interpolated_field(x, y, image)

    return x, y, image, field


def _get_field_parameters(image_path, edge_lengths, penumbra):
    x, y, image, field = _load_image_field_interpolator(image_path)
    field_centre, field_rotation = _get_pymedphys_field_centre_and_rotation(
        image_path, edge_lengths, penumbra
    )

    return {
        "x": x,
        "y": y,
        "image": image,
        "field": field,
        "pymedphys_field_centre": field_centre,
        "field_rotation": field_rotation,
    }


def _get_time_diffs(iview_datetimes, icom_datetimes):
    iview_datetimes = np.array(iview_datetimes)[:, None]
    icom_datetimes = np.array(icom_datetimes)[None, :]

    all_time_diffs = iview_datetimes - icom_datetimes

    time_diffs_pairs_index = np.argmin(np.abs(all_time_diffs), axis=1)
    max_time_diffs = np.take_along_axis(
        all_time_diffs, time_diffs_pairs_index[:, None], axis=1
    )

    if max_time_diffs.shape[1] != 1:
        raise ValueError("Expected last dimension to have collapsed")

    max_time_diffs = max_time_diffs[:, 0]

    alignment_time_diffs = pd.Series(
        max_time_diffs, name="time_diff"
    ).dt.total_seconds()

    return alignment_time_diffs


@st.cache
def _estimated_initial_deviation_to_apply(iview_datetimes, icom_datetimes):
    alignment_time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)

    sign_to_apply = np.sign(np.sum(alignment_time_diffs))
    deviation_to_apply = sign_to_apply * np.max(sign_to_apply * alignment_time_diffs)

    return datetime.timedelta(seconds=deviation_to_apply)


def _get_mean_based_offset(iview_datetimes, icom_datetimes):
    time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)
    new_offset = np.mean(time_diffs)

    return datetime.timedelta(seconds=new_offset)


def _get_mean_of_square_diffs(iview_datetimes, icom_datetimes):
    time_diffs = _get_time_diffs(iview_datetimes, icom_datetimes)
    return np.mean(np.square(time_diffs))


def _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes):
    def _icom_timestamp_minimiser(seconds):
        deviation_to_apply = datetime.timedelta(seconds=seconds[0])
        adjusted_icom_datetimes = icom_datetimes + deviation_to_apply

        return _get_mean_of_square_diffs(iview_datetimes, adjusted_icom_datetimes) * 10

    return _icom_timestamp_minimiser


@st.cache
def _determine_loop_offset(iview_datetimes, icom_datetimes):
    to_minimise = _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes)
    total_offset = datetime.timedelta(seconds=0)

    initial_deviation_to_apply = _estimated_initial_deviation_to_apply(
        iview_datetimes, icom_datetimes
    )
    total_offset += initial_deviation_to_apply
    icom_datetimes = icom_datetimes + initial_deviation_to_apply

    absolute_total_seconds_applied = np.abs(initial_deviation_to_apply.total_seconds())

    while absolute_total_seconds_applied > 0.00001:
        deviation_to_apply = _get_mean_based_offset(iview_datetimes, icom_datetimes)
        total_offset += deviation_to_apply
        icom_datetimes = icom_datetimes + deviation_to_apply

        absolute_total_seconds_applied = np.abs(deviation_to_apply.total_seconds())

    loop_offset = total_offset.total_seconds()
    loop_minimise_f = to_minimise([loop_offset])

    return loop_offset, loop_minimise_f


@st.cache
def _determine_basinhopping_offset(iview_datetimes, icom_datetimes):
    initial_deviation_to_apply = _estimated_initial_deviation_to_apply(
        iview_datetimes, icom_datetimes
    )

    to_minimise = _create_icom_timestamp_minimiser(iview_datetimes, icom_datetimes)
    result = scipy.optimize.basinhopping(
        to_minimise,
        [initial_deviation_to_apply.total_seconds()],
        T=1,
        niter=1000,
        niter_success=100,
        stepsize=10,
    )

    basinhopping_offset = result.x[0]
    basinhopping_minimise_f = to_minimise(result.x)

    return basinhopping_offset, basinhopping_minimise_f


def fix_bipolar_angle(angle: "pd.Series"):
    output = angle.to_numpy()
    output[output < 0] = output[output < 0] + 360

    output = pmp_transforms.convert_IEC_angle_to_bipolar(output)

    return output


def expand_border_events(mask):
    shifted_right = np.concatenate([[False], mask])
    shifted_left = np.concatenate([mask, [False]])

    combined = np.logical_or(shifted_right, shifted_left)

    return combined


def determine_speed(angle, time):
    diff_angle = np.diff(angle) / 360
    diff_time = pd.Series(np.diff(time)).dt.total_seconds().to_numpy() / 60

    rpm = diff_angle / diff_time

    return np.abs(rpm)


def get_collimator_and_gantry_flags(icom_datasets):
    gantry_rpm = determine_speed(icom_datasets["gantry"], icom_datasets["datetime"])
    collimator_rpm = determine_speed(
        icom_datasets["collimator"], icom_datasets["datetime"]
    )

    gantry_flag = gantry_rpm > GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
    gantry_flag = expand_border_events(gantry_flag)

    collimator_flag = (
        collimator_rpm > COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
    )
    collimator_flag = expand_border_events(collimator_flag)

    return gantry_flag, collimator_flag


def angle_speed_check(icom_datasets):
    gantry_flag, collimator_flag = get_collimator_and_gantry_flags(icom_datasets)

    if np.any(gantry_flag):
        raise ValueError("The gantry angle is changing faster than should be possible.")

    if np.any(collimator_flag):
        raise ValueError(
            "The collimator angle is changing faster than should be possible."
        )


def attempt_to_make_angle_continuous(
    time: "pd.Series",
    angle,
    speed_limit,
    init_range_to_adjust=0,
    max_range=5,
    range_iter=0.1,
):
    if init_range_to_adjust > max_range:
        raise ValueError("The adjustment range was larger than the maximum")

    within_adjustment_range = np.abs(angle) >= 180 - init_range_to_adjust
    outside_adjustment_range = np.invert(within_adjustment_range)

    if not np.any(outside_adjustment_range):
        raise ValueError("No data outside the safe angle bounds.")

    index_within = np.where(within_adjustment_range)[0]
    index_outside = np.where(np.invert(within_adjustment_range))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(index_within[:, None] - index_outside[None, :]), axis=1
    )

    closest_left_leaning = index_outside[where_closest_left_leaning]

    sign_to_be_adjusted = np.sign(angle[index_within]) != np.sign(
        angle[closest_left_leaning]
    )

    angles_to_be_adjusted = angle[index_within][sign_to_be_adjusted]
    angles_to_be_adjusted = angles_to_be_adjusted + 360 * np.sign(
        angle[closest_left_leaning][sign_to_be_adjusted]
    )

    angle[index_within[sign_to_be_adjusted]] = angles_to_be_adjusted

    rpm = determine_speed(angle, time)
    if np.any(rpm > speed_limit):
        angle = attempt_to_make_angle_continuous(
            time,
            angle,
            speed_limit,
            init_range_to_adjust=init_range_to_adjust + range_iter,
            max_range=max_range,
            range_iter=range_iter,
        )

    return angle


def _table_transfer_via_interpolation(source, location, key):
    interpolation = scipy.interpolate.interp1d(
        source["seconds_since_midnight"], source[key]
    )
    location[key] = interpolation(location["seconds_since_midnight"])


def _collapse_column_to_single_value(dataframe, column):
    results = dataframe[column].unique()
    if len(results) != 1:
        raise ValueError(f"Expected exactly one {column} per image")

    return results[0]
