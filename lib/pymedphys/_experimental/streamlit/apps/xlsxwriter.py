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
import io
import pathlib
import re

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st
from pymedphys._imports import xlsxwriter

from pymedphys._experimental.streamlit.apps.wlutz import _utilities

CATEGORY = "experimental"
TITLE = "Writing Excel Demo"

HOME = pathlib.Path.home()
PYMEDPHYS_LIBRARY_ROOT = pathlib.Path(__file__).parents[3]
LOGO_PATH = PYMEDPHYS_LIBRARY_ROOT.joinpath("_streamlit", "pymedphys-title.png")

FIGURE_CELL_HEIGHT = 15


def main():
    if st.button("Make demo.xlsx"):
        st.write(f"`{PYMEDPHYS_LIBRARY_ROOT}`")

        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 0])
        st.pyplot(fig)

        xlsx_filepath = HOME.joinpath(".pymedphys", "demo.xlsx")

        with io.BytesIO() as in_memory_file:
            with xlsxwriter.Workbook(xlsx_filepath) as workbook:
                worksheet = workbook.add_worksheet()
                worksheet.insert_image("A1", LOGO_PATH)

                fig.savefig(in_memory_file, format="png")
                worksheet.insert_image(
                    "A10", "a_plot.png", {"image_data": in_memory_file}
                )

        _insert_file_download_link(xlsx_filepath)

    st.write("## Writing Excel file from Wlutz results")

    (
        _,
        _,
        wlutz_directory_by_date,
        _,
        _,
        _,
    ) = _utilities.get_directories_and_initial_database(refresh_cache=False)

    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")

    st.write(f"`{raw_results_csv_path}`")

    try:
        dataframe = _get_results(raw_results_csv_path)
    except FileNotFoundError:
        st.error("Winston Lutz results not yet calculated/saved for this date.")
        st.stop()

    # st.write(raw_results_dataframe)

    # filtered = raw_results_dataframe
    # for column in ["treatment", "port", "algorithm"]:
    #     filtered = _filter_by_column(filtered, column)

    dataframe = dataframe.sort_values("seconds_since_midnight")

    # treatment = "00_06MV_0600DR"
    # filtered_by_treatment = _filter_by(dataframe, "treatment", treatment)

    # st.write(filtered_by_treatment)

    dataframe_by_algorithm = _filter_by(dataframe, "algorithm", "PyMedPhys")
    # st.write(dataframe_by_algorithm)

    statistics = []
    energies = dataframe_by_algorithm["energy"].unique()
    energies = sorted(energies, key=_natural_sort_key)

    column_direction_map = {"diff_x": "Transverse", "diff_y": "Radial"}
    for energy in energies:
        # st.write(energy)
        dataframe_by_energy = _filter_by(dataframe_by_algorithm, "energy", energy)

        # st.write(dataframe_by_energy["diff_x"])

        for column in ["diff_y", "diff_x"]:
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
    st.write(statistics)

    dataframe = dataframe.fillna("")

    wlutz_xlsx_filepath = wlutz_directory_by_date.joinpath("overview.xlsx")
    with xlsxwriter.Workbook(wlutz_xlsx_filepath) as workbook:
        summary_worksheet = workbook.add_worksheet(name="Summary")
        algorithm_worksheet = workbook.add_worksheet(name="Algorithms")
        raw_data_worksheet = workbook.add_worksheet(name="Raw Data")
        interpolated_data_worksheet = workbook.add_worksheet(name="Interpolated Data")

        # print(summary_worksheet, interpolated_data_worksheet)

        _write_data_get_references(
            data_column_start="A",
            data_header="Summary Statistics",
            dataframe=statistics,
            worksheet=summary_worksheet,
        )

        _create_algorithms_chart_sheet(
            dataframe, workbook, raw_data_worksheet, algorithm_worksheet
        )

    _insert_file_download_link(wlutz_xlsx_filepath)


def _filter_by(dataframe, column, value):
    filtered = dataframe.loc[dataframe[column] == value]

    return filtered


def _create_algorithms_chart_sheet(
    dataframe, workbook, raw_data_worksheet, algorithm_worksheet
):
    data_column_start = "A"
    figure_row = 1

    treatments = dataframe["treatment"].unique()
    treatments.sort()

    for treatment in treatments:
        filtered_by_treatment = _filter_by(dataframe, "treatment", treatment)

        ports = filtered_by_treatment["port"].unique()
        ports.sort()
        for port in ports:
            filtered_by_port = _filter_by(filtered_by_treatment, "port", port)

            chart_transverse = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )
            chart_radial = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )

            algorithms = filtered_by_port["algorithm"].unique()
            algorithms.sort()

            for algorithm in algorithms:
                filtered_by_algorithm = _filter_by(
                    filtered_by_port, "algorithm", algorithm
                )

                data_header = f"{treatment} | {port} | {algorithm}"

                references, data_column_start = _write_data_get_references(
                    data_column_start,
                    data_header,
                    filtered_by_algorithm[["gantry", "diff_x", "diff_y"]],
                    raw_data_worksheet,
                )

                chart_transverse.add_series(
                    {
                        "name": algorithm,
                        "categories": references["gantry"],
                        "values": references["diff_x"],
                    }
                )

                chart_radial.add_series(
                    {
                        "name": algorithm,
                        "categories": references["gantry"],
                        "values": references["diff_y"],
                    }
                )

            chart_transverse.set_title({"name": f"{treatment} | {port} | Transverse"})
            chart_transverse.set_x_axis({"name": "Gantry Angle (degrees)"})
            chart_transverse.set_y_axis({"name": "Field - BB (mm)"})

            chart_radial.set_title({"name": f"{treatment} | {port} | Radial"})
            chart_radial.set_x_axis({"name": "Gantry Angle (degrees)"})
            chart_radial.set_y_axis({"name": "Field - BB (mm)"})

            algorithm_worksheet.insert_chart(f"A{figure_row}", chart_radial)
            algorithm_worksheet.insert_chart(f"I{figure_row}", chart_transverse)
            figure_row += FIGURE_CELL_HEIGHT


def _write_data_get_references(
    data_column_start,
    data_header: str,
    dataframe: "pd.DataFrame",
    worksheet: "xlsxwriter.worksheet",
):
    # TODO: Make data header be on separate rows for easy querying by excel user.

    top_left_cell = f"{data_column_start}1"
    worksheet.write(top_left_cell, data_header)
    _, col = xlsxwriter.utility.xl_cell_to_rowcol(top_left_cell)

    columns = dataframe.columns
    last_row_number = len(dataframe) + 2
    last_col_letter_with_gap = xlsxwriter.utility.xl_col_to_name(col + len(columns) + 1)
    sheet_name = worksheet.name

    worksheet.write_row(f"{data_column_start}2", dataframe.columns)

    references = {}
    for i, column in enumerate(columns):
        series = dataframe[column]
        column_letter = xlsxwriter.utility.xl_col_to_name(col + i)
        worksheet.write_column(f"{column_letter}3", series)

        references[
            column
        ] = f"={sheet_name}!${column_letter}$3:${column_letter}${last_row_number}"

    return references, last_col_letter_with_gap


def _filter_by_column(dataframe, column):
    options = list(dataframe[column].unique())
    selected = st.radio(column, options)
    filtered = dataframe.loc[dataframe[column] == selected]

    return filtered


@st.cache()
def _get_results(filepath) -> "pd.DataFrame":
    raw_results_dataframe = pd.read_csv(filepath)

    return raw_results_dataframe


def _insert_file_download_link(filepath: pathlib.Path):
    with open(filepath, "rb") as f:
        contents = f.read()

    filename = filepath.name

    b64 = base64.b64encode(contents).decode()
    href = f"""
        <a href="data:file/zip;base64,{b64}" download='{filename}'>
            Click to download {filename}
        </a>
    """
    st.markdown(href, unsafe_allow_html=True)


# https://stackoverflow.com/a/16090640/3912576
def _natural_sort_key(s, _nsre=re.compile("([0-9]+)")):
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(s)]
