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
import functools

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys._wlutz import reporting

from pymedphys._experimental.streamlit.utilities import wlutz as _wlutz

from . import _altair, _utilities

RESULTS_DATA_COLUMNS = [
    "filepath",
    "algorithm",
    "diff_x",
    "diff_y",
    "field_centre_x",
    "field_centre_y",
    "bb_centre_x",
    "bb_centre_y",
]


def calculations_ui(
    database_table, database_directory, wlutz_directory_by_date, bb_diameter, penumbra
):
    st.write("## Calculations")

    ALGORITHM_FUNCTION_MAP = _wlutz.get_algorithm_function_map()

    algorithm_options = list(ALGORITHM_FUNCTION_MAP.keys())
    selected_algorithms = st.multiselect(
        "Algorithms to run", algorithm_options, algorithm_options
    )

    database_table["filename"] = database_table["filepath"].apply(
        _utilities.filepath_to_filename
    )
    database_table["time"] = database_table["datetime"].dt.time.apply(str)

    deviation_plot_threshold = st.number_input(
        "Display deviations greater than", value=0.2
    )

    plot_when_data_missing = st.checkbox("Plot when data missing", value=True)

    if st.button("Calculate"):
        run_calculation(
            database_table,
            database_directory,
            wlutz_directory_by_date,
            selected_algorithms,
            bb_diameter,
            penumbra,
            deviation_plot_threshold,
            plot_when_data_missing,
        )


def run_calculation(
    database_table,
    database_directory,
    wlutz_directory_by_date,
    selected_algorithms,
    bb_diameter,
    penumbra,
    deviation_plot_threshold,
    plot_when_data_missing,
):
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

    for progress_index, (_, database_row) in enumerate(database_table[::-1].iterrows()):
        relative_image_path = database_row["filepath"]

        if previously_calculated_results is not None:
            results = previously_calculated_results.loc[
                previously_calculated_results["filepath"] == relative_image_path
            ][RESULTS_DATA_COLUMNS]

            selected_algorithms_already_calculated = set(selected_algorithms).issubset(
                results["algorithm"].unique()
            )

        full_image_path = _get_full_image_path(database_directory, relative_image_path)
        edge_lengths, icom_field_rotation = _get_calculation_icom_items(database_row)

        if (
            previously_calculated_results is None
            or not selected_algorithms_already_calculated
        ):
            results = get_results_for_image(
                full_image_path,
                relative_image_path,
                selected_algorithms,
                bb_diameter,
                edge_lengths,
                icom_field_rotation,
                penumbra,
            )

        min_diff = results[["diff_x", "diff_y"]].min(axis=0)
        max_diff = results[["diff_x", "diff_y"]].max(axis=0)

        diff_range = max_diff - min_diff

        display_diagnostic_plot = np.any(diff_range > deviation_plot_threshold)
        if (
            plot_when_data_missing
            and results[["diff_x", "diff_y"]].isnull().values.any()
        ):
            display_diagnostic_plot = True

        if display_diagnostic_plot:
            st.write(results)
            st.write(database_row)

            figures = plot_diagnostic_figures(
                full_image_path,
                bb_diameter,
                edge_lengths,
                icom_field_rotation,
                penumbra,
                selected_algorithms,
            )

            for fig in figures:
                st.pyplot(fig)

        collated_results = collated_results.append(results)

        working_table = results.merge(
            database_table, left_on="filepath", right_on="filepath"
        )

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

        ratio_complete = (progress_index + 1) / total_files
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

    statistics_overview_csv_path = wlutz_directory_by_date.joinpath(statistics_filename)
    statistics_collection.to_csv(statistics_overview_csv_path, index=False)

    with open(statistics_overview_csv_path, "rb") as f:
        csv_bytes = f.read()

    b64 = base64.b64encode(csv_bytes).decode()
    href = f"""
        <a href=\"data:file/zip;base64,{b64}\" download='{statistics_filename}'>
            Download `{statistics_filename}`.
        </a>
    """
    st.markdown(href, unsafe_allow_html=True)


def _collapse_column_to_single_value(dataframe, column):
    results = dataframe[column].unique()
    if len(results) != 1:
        raise ValueError(f"Expected exactly one {column} per image")

    return results[0]


def _get_calculation_icom_items(database_row):
    edge_lengths = [database_row["width"], database_row["length"]]
    icom_field_rotation = -database_row["collimator"]

    return edge_lengths, icom_field_rotation


def get_results_for_image(
    full_image_path,
    relative_image_path,
    selected_algorithms,
    bb_diameter,
    edge_lengths,
    icom_field_rotation,
    penumbra,
):

    results_data = []

    for algorithm in selected_algorithms:

        field_centre, bb_centre = _calculate_wlutz(
            full_image_path,
            algorithm,
            bb_diameter,
            edge_lengths,
            penumbra,
            icom_field_rotation,
        )
        results_data.append(
            {
                "filepath": relative_image_path,
                "algorithm": algorithm,
                "diff_x": field_centre[0] - bb_centre[0],
                "diff_y": field_centre[1] - bb_centre[1],
                "field_centre_x": field_centre[0],
                "field_centre_y": field_centre[1],
                "bb_centre_x": bb_centre[0],
                "bb_centre_y": bb_centre[1],
            }
        )

    results = pd.DataFrame.from_dict(results_data)

    if set(results.columns) != set(RESULTS_DATA_COLUMNS):
        raise ValueError("Unexpected columns")

    return results


def plot_diagnostic_figures(
    full_image_path,
    bb_diameter,
    edge_lengths,
    icom_field_rotation,
    penumbra,
    selected_algorithms,
):
    x, y, image = _wlutz.load_iview_image(full_image_path)

    figures = []

    for algorithm in selected_algorithms:
        field_centre, bb_centre = _calculate_wlutz(
            full_image_path,
            algorithm,
            bb_diameter,
            edge_lengths,
            penumbra,
            icom_field_rotation,
        )

        try:
            fig, axs = reporting.image_analysis_figure(
                x,
                y,
                image,
                bb_centre,
                field_centre,
                icom_field_rotation,
                bb_diameter,
                edge_lengths,
                penumbra,
            )

            axs[0, 0].set_title(algorithm)
            figures.append(fig)
        except ValueError as e:
            st.write(e)

    return figures


def _get_full_image_path(database_directory, relative_image_path):
    return database_directory.joinpath(relative_image_path)


@st.cache(show_spinner=False)
def _calculate_wlutz(
    image_path, algorithm, bb_diameter, edge_lengths, penumbra, icom_field_rotation
):
    field_centre, bb_centre = _wlutz.calculate(
        image_path, algorithm, bb_diameter, edge_lengths, penumbra, icom_field_rotation
    )

    return field_centre, bb_centre
