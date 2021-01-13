# Copyright (C) 2020-2021 Cancer Care Associates

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

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import xlsxwriter

from . import _utilities

FIGURE_CELL_HEIGHT = 15


def write_excel_overview(dataframe, statistics, filepath):
    dataframe = dataframe.fillna("")

    with xlsxwriter.Workbook(filepath) as workbook:
        summary_worksheet = workbook.add_worksheet(name="Summary")
        algorithm_worksheet = workbook.add_worksheet(name="Algorithms")
        raw_data_worksheet = workbook.add_worksheet(name="Raw Data")

        _write_data_get_references(
            data_column_start="A",
            data_header="Summary Statistics",
            dataframe=statistics,
            worksheet=summary_worksheet,
        )

        _create_algorithms_chart_sheet(
            dataframe, workbook, raw_data_worksheet, algorithm_worksheet
        )

    _insert_file_download_link(filepath)


def _create_algorithms_chart_sheet(
    dataframe, workbook, raw_data_worksheet, algorithm_worksheet
):
    data_column_start = "A"
    figure_row = 1

    treatments = dataframe["treatment"].unique()
    treatments.sort()

    for treatment in treatments:
        filtered_by_treatment = _utilities.filter_by(dataframe, "treatment", treatment)

        ports = filtered_by_treatment["port"].unique()
        ports.sort()
        for port in ports:
            filtered_by_port = _utilities.filter_by(filtered_by_treatment, "port", port)

            chart_transverse = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )
            chart_radial = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )

            algorithms = filtered_by_port["algorithm"].unique()
            algorithms.sort()

            for algorithm in algorithms:
                filtered_by_algorithm = _utilities.filter_by(
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
