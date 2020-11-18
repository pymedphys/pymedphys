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


from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pylinac
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit.apps.wlutz import _dbf, _filtering, _frames
from pymedphys._streamlit.utilities import misc
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api
from pymedphys._wlutz import reporting


def read_image(path):
    return lljpeg.imread(path)


def main():
    st.title("Winston-Lutz Arc")

    st.sidebar.write("## Parameters")

    width = st.sidebar.number_input("Width (mm)", 20)
    length = st.sidebar.number_input("Length (mm)", 24)
    edge_lengths = [width, length]

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", 8)
    penumbra = st.sidebar.number_input("Penumbra (mm)", 2)

    _, database_directory = misc.get_site_and_directory("Database Site", "iviewdb")

    st.write("## Load iView databases for a given date")
    refresh_cache = st.button("Re-query databases")
    merged = _dbf.load_and_merge_dbfs(database_directory, refresh_cache)

    st.write("## Filtering")
    filtered = _filtering.filter_image_sets(merged)
    filtered.sort_values("datetime", ascending=False, inplace=True)

    st.write(filtered)

    if len(filtered) == 0:
        st.stop()

    st.write("## Loading database image frame data")

    try:
        database_table = _frames.dbf_frame_based_database(
            database_directory, refresh_cache, filtered
        )
    except FileNotFoundError:
        database_table = _frames.xml_frame_based_database(database_directory, filtered)

    st.write(database_table)

    algorithm_options = ["PyMedPhys", "PyLinac"]
    selected_algorithms = st.multiselect(
        "Algorithms to run", algorithm_options, algorithm_options
    )

    show_selected_image = st.checkbox(
        "Select a single image to show results for", False
    )

    if show_selected_image:
        relative_image_path = st.selectbox("Select single filepath", table["filepath"])

        results = _get_results_for_image(
            database_directory,
            relative_image_path,
            selected_algorithms,
            bb_diameter,
            edge_lengths,
            penumbra,
        )

        st.write(results)

        _plot_diagnostic_figures(
            database_directory,
            relative_image_path,
            bb_diameter,
            edge_lengths,
            penumbra,
            selected_algorithms,
        )

    if st.button("Calculate"):
        progress_bar = st.progress(0)
        status_text = st.empty()

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
            )[["datetime", "diff_x", "diff_y", "algorithm"]]
            working_table.set_index("datetime", inplace=True)

            for algorithm in selected_algorithms:
                working_table_for_algorithm = working_table.loc[
                    working_table["algorithm"] == algorithm
                ]
                working_table_for_algorithm.drop("algorithm", axis=1, inplace=True)

                try:
                    chart_bucket[algorithm].add_rows(working_table_for_algorithm)
                except KeyError:
                    st.write(f"### {algorithm}")
                    line_chart = st.line_chart(working_table_for_algorithm)
                    chart_bucket[algorithm] = line_chart

            ratio_complete = (i + 1) / total_files
            progress_bar.progress(ratio_complete)

            percent_complete = round(ratio_complete * 100, 2)
            status_text.text(f"{percent_complete}% Complete")


def _plot_algorithm_by_time(diff_table, database_table, algorithm):
    working_table = diff_table.loc[diff_table["algorithm"] == algorithm]
    working_table = working_table.merge(
        database_table, left_on="filepath", right_on="filepath"
    )[["datetime", "diff_x", "diff_y"]]

    working_table.set_index("datetime", inplace=True)
    st.write(working_table)
    st.line_chart(working_table)


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

    for algorithm in selected_algorithms:
        field_centre, _, bb_centre = _calculate_wlutz(
            full_image_path, algorithm, bb_diameter, edge_lengths, penumbra
        )

        fig, axs = _create_figure(field_centre, bb_centre, wlutz_input_parameters)
        axs[0, 0].set_title(algorithm)
        st.pyplot(fig)


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


@st.cache
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


@st.cache
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
    raw_image = read_image(image_path)
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
