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


import base64
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys._utilities import filesystem as _pp_filesystem_utilities

from pymedphys._experimental.wlutz import main as _wlutz
from pymedphys._experimental.wlutz import reporting as _reporting

from . import _altair

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

# Draw a plot within the app when algorithms deviate from each other
# by this much
DEFAULT_INTER_ALGORITHM_DEVIATION_PLOT_THRESHOLD = 0.5  # mm

# Draw a plot within the app when the total deviation from the origin
# is more than this much
DEFAULT_TOTAL_DEVIATION_PLOT_THRESHOLD = 1.5  # mm

# Draw a plot when an algorithm doesn't return a result
DEFAULT_PLOT_WHEN_DATA_IS_MISSING = False

# Whether or not the app should "march on" in the face of an error or
# produce a traceback. When it "marches on" it will not produce data
# points in the locations where an error occurred.
DEFAULT_FILL_ERRORS_WITH_NAN = True


def calculations_ui(
    database_table,
    database_directory,
    wlutz_directory_by_date,
    bb_diameter,
    penumbra,
    advanced_mode,
    loosened_internal_tolerances,
    quiet=False,
):
    """The WLutz streamlit calculation UI

    Parameters
    ----------
    database_table
    database_directory
    wlutz_directory_by_date
    bb_diameter
    penumbra
    advanced_mode
    loosened_internal_tolerances
        Whether or not to use a 'less strict' version of PyMedPhys'
        WLutz algorithm. This is to handle the lower contrast when
        trying to find an air cavity instead of ball bearing.
    quiet : bool, optional
        Run the calculation UI with minimal feedback. This mode is
        designed for use in Daily QA where all the extra
        "physics feedback" will get in the way.

    Returns
    -------
    statistics_collection

    """
    if not quiet:
        st.write("## Calculations")

        st.write("### Calculation options")

    if not advanced_mode and not quiet:
        st.write("*Calculation options are available by ticking advanced mode*")

    if advanced_mode:
        plot_x_axis = st.radio("Plot x-axis", ["Gantry", "Collimator", "Time"])
    else:
        plot_x_axis = "Gantry"

    ALGORITHM_FUNCTION_MAP = _wlutz.get_algorithm_function_map()

    loosened_tolerance_names = ["PyMedPhys-LoosenedTolerance", "PyMedPhys-NoTolerance"]

    if loosened_internal_tolerances:
        if quiet:
            algorithm_options = loosened_tolerance_names[0:1]
        else:
            algorithm_options = loosened_tolerance_names
    else:
        algorithm_options = list(
            set(ALGORITHM_FUNCTION_MAP.keys()).difference(loosened_tolerance_names)
        )

    if advanced_mode:
        selected_algorithms = st.multiselect(
            "Algorithms to run", algorithm_options, algorithm_options
        )
    else:
        selected_algorithms = algorithm_options

    database_table["filename"] = database_table["filepath"].apply(_filepath_to_filename)
    database_table["time"] = database_table["datetime"].dt.time.apply(str)

    if quiet:
        default_data_missing_plot = False
    elif loosened_internal_tolerances:
        default_data_missing_plot = True
    else:
        default_data_missing_plot = DEFAULT_PLOT_WHEN_DATA_IS_MISSING

    if quiet:
        default_deviation_plot_threshold = np.inf
        default_total_deviation_plot_threshold = np.inf

    else:
        default_deviation_plot_threshold = (
            DEFAULT_INTER_ALGORITHM_DEVIATION_PLOT_THRESHOLD
        )

        if loosened_internal_tolerances:
            default_total_deviation_plot_threshold = 3.0
        else:
            default_total_deviation_plot_threshold = (
                DEFAULT_TOTAL_DEVIATION_PLOT_THRESHOLD
            )

    if advanced_mode:
        deviation_plot_threshold = st.number_input(
            "Display inter-algorithm deviations greater than",
            value=default_deviation_plot_threshold,
        )
        total_deviation_plot_threshold = st.number_input(
            "Display total deviations greater than",
            value=default_total_deviation_plot_threshold,
        )

        plot_when_data_missing = st.checkbox(
            "Plot when data missing", value=default_data_missing_plot
        )
        fill_errors_with_nan = st.checkbox(
            "Fill errors with nan", value=DEFAULT_FILL_ERRORS_WITH_NAN
        )
    else:
        deviation_plot_threshold = default_deviation_plot_threshold
        total_deviation_plot_threshold = default_total_deviation_plot_threshold
        plot_when_data_missing = default_data_missing_plot
        fill_errors_with_nan = DEFAULT_FILL_ERRORS_WITH_NAN

    if not quiet:
        st.write("### Run calculations")
        calculate = st.button("Calculate")

    if quiet or calculate:
        return run_calculation(
            database_table,
            database_directory,
            wlutz_directory_by_date,
            selected_algorithms,
            bb_diameter,
            penumbra,
            deviation_plot_threshold,
            total_deviation_plot_threshold,
            plot_when_data_missing,
            advanced_mode,
            plot_x_axis,
            fill_errors_with_nan,
            quiet=quiet,
        )

    return None


def run_calculation(
    database_table,
    database_directory,
    wlutz_directory_by_date,
    selected_algorithms,
    bb_diameter,
    penumbra,
    deviation_plot_threshold,
    total_deviation_plot_threshold,
    plot_when_data_missing,
    advanced_mode,
    plot_x_axis,
    fill_errors_with_nan,
    quiet,
):
    xlim = (-180, 180)
    ylim = (-2, 2)

    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")
    try:
        previously_calculated_results = pd.read_csv(
            raw_results_csv_path, index_col=False
        )
    except FileNotFoundError:
        previously_calculated_results = None

    if not quiet:
        st.sidebar.write("## Progress")
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
                fill_errors_with_nan,
            )

        columns_to_check_for_deviation = [
            "diff_x",
            "diff_y",
            "field_centre_x",
            "field_centre_y",
            "bb_centre_x",
            "bb_centre_y",
        ]

        for column in columns_to_check_for_deviation:
            results[column] = pd.to_numeric(results[column])

        min_result = results[columns_to_check_for_deviation].min(axis=0)
        max_result = results[columns_to_check_for_deviation].max(axis=0)

        result_range = max_result - min_result

        diff_columns = ["diff_x", "diff_y"]
        max_diff = np.max(np.abs(results[diff_columns]))

        a_deviation_is_larger_than_threshold = np.any(
            result_range > deviation_plot_threshold
        ) or np.any(max_diff > total_deviation_plot_threshold)
        at_least_one_diff_is_missing = (
            results[["diff_x", "diff_y"]].isnull().values.any()
        )
        all_diffs_are_missing = results[["diff_x", "diff_y"]].isnull().values.all()

        if plot_when_data_missing and at_least_one_diff_is_missing:
            display_diagnostic_plot = True
        elif a_deviation_is_larger_than_threshold and not all_diffs_are_missing:
            display_diagnostic_plot = True

            if display_diagnostic_plot:
                st.write(result_range)
        else:
            display_diagnostic_plot = False

        if display_diagnostic_plot:
            st.write(results)
            st.write(database_row)

            figures = plot_diagnostic_figures(
                full_image_path,
                results,
                icom_field_rotation,
                bb_diameter,
                edge_lengths,
                penumbra,
            )

            columns = st.beta_columns(len(figures))
            for fig, col in zip(figures, columns):
                with col:
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
            if not quiet:
                st.write(f"### Treatment: `{treatment}` | Port: `{port}`")

            port_chart_bucket = _altair.build_both_axis_altair_charts(
                table_filtered_by_port, plot_x_axis, quiet=quiet, xlim=xlim, ylim=ylim
            )
            treatment_chart_bucket[port] = port_chart_bucket

        if not quiet:
            ratio_complete = (progress_index + 1) / total_files
            progress_bar.progress(ratio_complete)

            percent_complete = round(ratio_complete * 100, 2)
            status_text.text(f"{percent_complete}% Complete")

    contextualised_results: pd.DataFrame = collated_results.merge(
        database_table, left_on="filepath", right_on="filepath"
    )

    if advanced_mode:
        st.write("## Raw results")
        st.write(contextualised_results)

    wlutz_directory_by_date.mkdir(parents=True, exist_ok=True)

    merged_with_previous = pd.concat(
        [contextualised_results, previously_calculated_results]
    )

    merged_with_previous = merged_with_previous.round(
        {
            "diff_x": 4,
            "diff_y": 4,
            "field_centre_x": 4,
            "field_centre_y": 4,
            "bb_centre_x": 4,
            "bb_centre_y": 4,
            "width": 1,
            "length": 1,
            "collimator": 1,
            "gantry": 1,
        }
    )

    merged_with_previous = merged_with_previous.drop_duplicates(
        subset=["filepath", "algorithm"]
    )
    merged_with_previous.to_csv(raw_results_csv_path, index=False)

    statistics_collection = []

    for treatment, treatment_chart_bucket in chart_bucket.items():
        for port, port_chart_bucket in treatment_chart_bucket.items():
            for column, orientation in zip(
                ["diff_x", "diff_y"], ["Transverse", "Radial"]
            ):
                plot_filename = f"{treatment}-{port}-{orientation}.png"
                plot_filename = _pp_filesystem_utilities.make_a_valid_directory_name(
                    plot_filename
                )
                plot_filepath = wlutz_directory_by_date.joinpath(plot_filename)

                mask = (contextualised_results["treatment"] == treatment) & (
                    contextualised_results["port"] == port
                )

                masked = contextualised_results.loc[mask]

                fig, ax = plt.subplots()

                energies = masked["energy"].unique()
                for energy in energies:
                    energy_masked = masked.loc[masked["energy"] == energy]
                    for algorithm in sorted(selected_algorithms):
                        algorithm_masked = energy_masked.loc[
                            energy_masked["algorithm"] == algorithm
                        ]
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
                        description["energy"] = energy
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
                plt.close(fig)

    statistics_collection = pd.concat(statistics_collection, axis=1).T
    statistics_collection.reset_index(inplace=True)
    statistics_collection = statistics_collection[
        [
            "energy",
            "orientation",
            "min",
            "max",
            "mean",
            "treatment",
            "port",
            "algorithm",
        ]
    ]

    if advanced_mode:
        st.write("## Overview Statistics")
        st.write(statistics_collection)

    statistics_filename = "statistics_overview.csv"

    statistics_overview_csv_path = wlutz_directory_by_date.joinpath(statistics_filename)
    statistics_collection.to_csv(statistics_overview_csv_path, index=False)

    with open(statistics_overview_csv_path, "rb") as f:
        csv_bytes = f.read()

    if advanced_mode:
        b64 = base64.b64encode(csv_bytes).decode()
        href = f"""
            <a href=\"data:file/zip;base64,{b64}\" download='{statistics_filename}'>
                Download `{statistics_filename}`.
            </a>
        """
        st.markdown(href, unsafe_allow_html=True)

    return statistics_collection


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
    fill_errors_with_nan,
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
            fill_errors_with_nan,
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
    full_image_path, results, icom_field_rotation, bb_diameter, edge_lengths, penumbra
):
    x, y, image = _wlutz.load_iview_image(full_image_path)

    figures = []

    for _, results_row in results.iterrows():
        field_centre, bb_centre = (
            [results_row["field_centre_x"], results_row["field_centre_y"]],
            [results_row["bb_centre_x"], results_row["bb_centre_y"]],
        )

        try:
            fig, axs = _reporting.image_analysis_figure(
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

            axs[0, 0].set_title(results_row["algorithm"])
            figures.append(fig)
        except ValueError as e:
            st.write(e)

    return figures


def _get_full_image_path(database_directory, relative_image_path):
    return database_directory.joinpath(relative_image_path)


@st.cache(show_spinner=False)
def _calculate_wlutz(
    image_path,
    algorithm,
    bb_diameter,
    edge_lengths,
    penumbra,
    icom_field_rotation,
    fill_errors_with_nan,
):
    field_centre, bb_centre = _wlutz.calculate(
        image_path,
        algorithm,
        bb_diameter,
        edge_lengths,
        penumbra,
        icom_field_rotation,
        fill_errors_with_nan=fill_errors_with_nan,
    )

    return field_centre, bb_centre


def _filepath_to_filename(path):
    path = pathlib.Path(path)
    filename = path.name

    return filename
