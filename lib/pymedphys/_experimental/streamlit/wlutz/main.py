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

import pathlib

import altair as alt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pylinac
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit.utilities import misc
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api
from pymedphys._wlutz import reporting

from . import _dbf, _filtering, _frames


def main():
    """The entrance function for the WLutz Arc Streamlit GUI.

    This GUI connects to an iViewDB stored on a shared network drive
    and allows users to plot the difference between the field centre
    and the ball bearing centre accross a range of gantry angles.

    """
    st.title("Winston-Lutz Arc")

    edge_lengths, bb_diameter, penumbra = _set_parameters()

    _, database_directory = misc.get_site_and_directory("Database Site", "iviewdb")

    st.write("## Load iView databases for a given date")
    refresh_cache = st.button("Re-query databases")

    database_table = _load_database_with_cache(database_directory, refresh_cache)
    database_table = _get_user_image_set_selection(database_table)
    database_table = _load_image_frame_database(
        database_directory, database_table, refresh_cache
    )

    st.write(database_table)

    algorithm_options = ["PyMedPhys", "PyLinac"]
    selected_algorithms = st.multiselect(
        "Algorithms to run", algorithm_options, algorithm_options
    )

    database_table["filename"] = database_table["filepath"].apply(_filepath_to_filename)
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
            # to be overlayed.
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
                        port_chart_bucket = _build_both_axis_altair_charts(
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

        if _filepath_to_filename(relative_image_path) != image_filename:
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


def _build_both_axis_altair_charts(table):
    chart_bucket = {}

    for axis in ["y", "x"]:
        raw_chart = _build_altair_chart(table, axis)
        chart_bucket[axis] = st.altair_chart(raw_chart, use_container_width=True)

    return chart_bucket


def _build_altair_chart(table, axis):
    parameters = {
        "x": {
            "column-name": "diff_x",
            "axis-name": "X-axis",
            "plot-type": "Transverse",
        },
        "y": {"column-name": "diff_y", "axis-name": "Y-axis", "plot-type": "Radial"},
    }[axis]

    raw_chart = (
        alt.Chart(table)
        .mark_line(point=True)
        .encode(
            x=alt.X("datetime", axis=alt.Axis(title="Image Time")),
            y=alt.Y(
                parameters["column-name"],
                axis=alt.Axis(
                    title=f"iView {parameters['axis-name']} (mm) [Field - BB]"
                ),
            ),
            color=alt.Color("algorithm", legend=alt.Legend(title="Algorithm")),
            tooltip=["time", "diff_x", "diff_y", "filename", "algorithm"],
        )
    ).properties(title=parameters["plot-type"])

    return raw_chart


def _filepath_to_filename(path):
    path = pathlib.Path(path)
    filename = path.name

    return filename


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
