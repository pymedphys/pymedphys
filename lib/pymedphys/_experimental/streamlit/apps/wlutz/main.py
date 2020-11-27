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
from pymedphys._imports import pylinac, scipy
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._experimental.streamlit.utilities import icom as _icom
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc
from pymedphys._utilities import transforms as pmp_transforms
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api
from pymedphys._wlutz import reporting

from . import _altair, _dbf, _filtering, _frames, _utilities

GANTRY_EXPECTED_SPEED_LIMIT = 1  # RPM
COLLIMATOR_EXPECTED_SPEED_LIMIT = 2.7  # RPM
NOISE_BUFFER_FACTOR = 5  # To allow a noisy point to not trigger the speed limit
TOTAL_TIME_BUFFER_FACTOR = 0.8

QUESTIONABLE_SIGN_DISTANCE = 5  # Angle about +/-180 where the sign is in question
GANTRY_TIME_TO_FLIP_SIGN = (
    (360 - 2 * QUESTIONABLE_SIGN_DISTANCE)
    / 360
    / GANTRY_EXPECTED_SPEED_LIMIT
    * TOTAL_TIME_BUFFER_FACTOR
) * 60  # seconds
COLLIMATOR_TIME_TO_FLIP_SIGN = (
    (360 - 2 * QUESTIONABLE_SIGN_DISTANCE)
    / 360
    / COLLIMATOR_EXPECTED_SPEED_LIMIT
    * TOTAL_TIME_BUFFER_FACTOR
) * 60  # seconds


def main():
    """The entrance function for the WLutz Arc Streamlit GUI.

    This GUI connects to an iViewDB stored on a shared network drive
    and allows users to plot the difference between the field centre
    and the ball bearing centre accross a range of gantry angles.

    """
    st.title("Winston-Lutz Arc")

    edge_lengths, bb_diameter, penumbra = _set_parameters()

    site_directories = _config.get_site_directories()
    chosen_site = misc.site_picker("Site")

    database_directory = site_directories[chosen_site]["iviewdb"]

    icom_directory = site_directories[chosen_site]["icom"]
    icom_patients_directory = icom_directory.joinpath("patients")

    st.write("## Load iView databases for a given date")
    refresh_cache = st.button("Re-query databases")

    database_table = _load_database_with_cache(database_directory, refresh_cache)
    database_table = _get_user_image_set_selection(database_table)
    database_table = _load_image_frame_database(
        database_directory, database_table, refresh_cache
    )

    # Map iview machine id alias to name
    config = _config.get_config()
    linac_map = {site["name"]: site["linac"] for site in config["site"]}

    alias_map = {}
    for linac in linac_map[chosen_site]:
        try:
            alias_map[linac["aliases"]["iview"]] = linac["name"]
        except KeyError:
            alias_map[linac["name"]] = linac["name"]

    database_table["machine_id"] = database_table["machine_id"].apply(
        lambda x: alias_map[x]
    )

    st.write(database_table)

    # --

    st.write("## iView to iCom timestamp alignment")

    selected_date = database_table["datetime"].dt.date.unique()
    if len(selected_date) != 1:
        raise ValueError("Expected only one date")

    selected_date = selected_date[0]

    selected_machine_id = database_table["machine_id"].unique()
    if len(selected_machine_id) != 1:
        raise ValueError("Expected only one machine id")

    selected_machine_id = selected_machine_id[0]

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
            "increasing the number of imaging frames (such as provided "
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
        icom_datasets.append(_icom.get_icom_dataset(filepath))

    icom_datasets = pd.concat(icom_datasets, axis=0, ignore_index=True)
    icom_datasets.sort_values(by="datetime", inplace=True)

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
        .mark_area(opacity=0.1, color="black")
        .encode(x="datetime:T", y="beam_shade_min:Q", y2="beam_shade_max:Q")
    )

    st.altair_chart(beam_on_chart, use_container_width=True)

    st.write(icom_datasets)
    # icom_datasets["gantry"] = fix_bipolar_angle(icom_datasets["gantry"])
    # icom_datasets["collimator"] = fix_bipolar_angle(icom_datasets["collimator"])

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
                y=alt.Y("angle:Q", axis=alt.Axis(title=f"Angle (degrees)")),
                color="device:N",
                tooltip=["time:N", "device:N", "angle:Q"],
            )
            .properties(title="iCom Angle Parameters")
            .interactive(bind_y=False)
        )
    ).configure_point(size=5)

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

    # TODO: Need to handle the improper wrap-around of the iCom bipolar
    # parameters

    gantry_flag, collimator_flag = get_collimator_and_gantry_flags(icom_datasets)

    # TODO: for each flag, find the next left most "safe angle" (< |175|), and also
    # find the next right most "safe angle". Make an "index pair" for each flag.
    # This defines the "unsafe" bounds caused by a flag. Add these index pairs to a set
    # so at to make sure their unique. Iterate over each bound index and find the sign
    # of the bounds. If the sign is different, raise an error, if the sign is the
    # same apply that sign to the lot.
    # Safe angle, groups also need to be divided by "time gaps", if enough time has
    # gone by between consecutive steps such that a sufficient rotation to flip the
    # sign could have occurred, end the group there. (or something like that).

    st.write(GANTRY_TIME_TO_FLIP_SIGN)
    st.write(COLLIMATOR_TIME_TO_FLIP_SIGN)

    angle_speed_check(icom_datasets)

    # scipy.interpolate.interp1d()

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
        database_directory,
        database_table,
        selected_algorithms,
        bb_diameter,
        edge_lengths,
        penumbra,
    )

    if st.button("Calculate"):
        st.sidebar.write("---\n## Progress")
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()

        collated_results = pd.DataFrame()
        chart_bucket = {}

        total_files = len(database_table["filepath"])

        for i, relative_image_path in enumerate(database_table["filepath"][::-1]):
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

            treatments = working_table["treatment"].unique()
            ports = working_table["port"].unique()

            # TODO: Provide a selectbox that allows certain treatment/ports
            # to be overlaid.
            for treatment in treatments:
                try:
                    treatment_chart_bucket = chart_bucket[treatment]
                except KeyError:
                    chart_bucket[treatment] = {}
                    treatment_chart_bucket = chart_bucket[treatment]

                table_filtered_by_treatment = working_table.loc[
                    working_table["treatment"] == treatment
                ]

                for port in ports:
                    table_filtered_by_port = table_filtered_by_treatment.loc[
                        table_filtered_by_treatment["port"] == port
                    ]
                    try:
                        for axis in ["y", "x"]:
                            treatment_chart_bucket[port][axis].add_rows(
                                table_filtered_by_port
                            )
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


def _show_selected_image(
    database_directory,
    database_table,
    selected_algorithms,
    bb_diameter,
    edge_lengths,
    penumbra,
):
    show_selected_image = st.checkbox(
        "Select a single image to show results for", False
    )

    filenames = list(database_table["filename"])

    if show_selected_image:
        image_filename = st.selectbox("Select single filepath", filenames)

        st.write(image_filename)

        relative_image_path = database_table.loc[
            database_table["filename"] == image_filename
        ]["filepath"]
        if len(relative_image_path) != 1:
            raise ValueError("Filepath and filelength should be a one-to-one mapping")

        relative_image_path = relative_image_path.iloc[0]

        if _utilities.filepath_to_filename(relative_image_path) != image_filename:
            raise ValueError("Filepath selection did not convert appropriately")

        st.write(relative_image_path)

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

    width = st.sidebar.number_input("Width (mm)", 20)
    length = st.sidebar.number_input("Length (mm)", 24)
    edge_lengths = [width, length]

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", 8)
    penumbra = st.sidebar.number_input("Penumbra (mm)", 2)

    return edge_lengths, bb_diameter, penumbra


def _load_database_with_cache(database_directory, refresh_cache):
    merged = _dbf.load_and_merge_dbfs(database_directory, refresh_cache)

    return merged


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

        field_centre, field_rotation, bb_centre = _calculate_wlutz(
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
                "field_rotation": field_rotation,
                "bb_centre_x": bb_centre[0],
                "bb_centre_y": bb_centre[1],
            }
        )

    results = pd.DataFrame.from_dict(results_data)

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


def get_collimator_and_gantry_flags(icom_datasets):
    diff_gantry = np.diff(icom_datasets["gantry"]) / 360  # Rotations
    diff_coll = np.diff(icom_datasets["collimator"]) / 360  # Rotations
    diff_time = (
        pd.Series(np.diff(icom_datasets["datetime"])).dt.total_seconds().to_numpy()
        / 60  # Minutes
    )

    gantry_rpm = diff_gantry / diff_time
    collimator_rpm = diff_coll / diff_time

    gantry_flag = np.abs(gantry_rpm) > GANTRY_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
    gantry_flag = expand_border_events(gantry_flag)

    collimator_flag = (
        np.abs(collimator_rpm) > COLLIMATOR_EXPECTED_SPEED_LIMIT * NOISE_BUFFER_FACTOR
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


# def attempt_to_make_angle_continuous(angle: "pd.Series"):
#     output = angle.to_numpy()

#     maximum_overshoot = 3


#     if np.all(angle == 180):
#         return angle

#     angle[angle > 180] = angle[angle > 180] - 360

#     is_180 = np.where(angle == 180)[0]
#     not_180 = np.where(np.invert(angle == 180))[0]

#     where_closest_left_leaning = np.argmin(
#         np.abs(is_180[:, None] - not_180[None, :]), axis=1
#     )
#     where_closest_right_leaning = (
#         len(not_180)
#         - 1
#         - np.argmin(np.abs(is_180[::-1, None] - not_180[None, ::-1]), axis=1)[::-1]
#     )

#     closest_left_leaning = not_180[where_closest_left_leaning]
#     closest_right_leaning = not_180[where_closest_right_leaning]

#     assert np.all(
#         np.sign(angle[closest_left_leaning]) == np.sign(angle[closest_right_leaning])
#     ), "Unable to automatically determine whether angle is 180 or -180"

#     angle[is_180] = np.sign(angle[closest_left_leaning]) * angle[is_180]

#     return angle