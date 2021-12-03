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
from collections import defaultdict
from typing import Dict

from pymedphys._imports import natsort
from pymedphys._imports import pandas as pd  # pylint: disable = unused-import
from pymedphys._imports import streamlit as st
from pymedphys._imports import xlsxwriter

from pymedphys._experimental.streamlit.utilities import iteration as _iteration

FIGURE_CELL_HEIGHT = 15
FIGURE_CELL_WIDTH = 8


def write_excel_overview(dataframe, statistics, filepath):
    dataframe = dataframe.fillna("")

    energy_to_treatments_map = defaultdict(lambda: [])
    for treatment in dataframe["treatment"].unique():
        dataframe_by_treatment = _iteration.filter_by(dataframe, "treatment", treatment)
        energies = dataframe_by_treatment["energy"].unique()
        if len(energies) != 1:
            raise ValueError("Expected exactly one energy per Treatment ID")

        energy = energies[0]
        energy_to_treatments_map[energy].append(treatment)

    with xlsxwriter.Workbook(filepath) as workbook:
        summary_worksheet = workbook.add_worksheet(name="Summary")
        algorithm_worksheet = workbook.add_worksheet(name="Algorithms")
        raw_data_worksheet = workbook.add_worksheet(name="Raw Data")

        references = _write_diff_data(dataframe, raw_data_worksheet)
        # st.write(references)

        _create_algorithms_chart_sheet(workbook, algorithm_worksheet, references)
        _create_overview_sheet(
            workbook,
            summary_worksheet,
            references,
            statistics,
            energy_to_treatments_map,
        )

    _insert_file_download_link(filepath)


def _write_diff_data(
    dataframe: "pd.DataFrame", worksheet: "xlsxwriter.worksheet.Worksheet"
):
    data = {"column_start": "A", "references": {}, "worksheet": worksheet}

    def _treatment_callback(_dataframe, data, treatment):
        data["references"][treatment] = {}

    def _port_callback(_dataframe, data, treatment, port):
        data["references"][treatment][port] = {}

    def _algorithm_callback(dataframe, data, treatment, port, algorithm):
        data_header = {"treatment": treatment, "port": port, "algorithm": algorithm}

        (
            data["references"][treatment][port][algorithm],
            data["column_start"],
        ) = _write_data_get_references(
            data["column_start"],
            data_header,
            dataframe[["gantry", "diff_x", "diff_y"]],
            data["worksheet"],
        )

    columns = ["treatment", "port", "algorithm"]
    callbacks = [_treatment_callback, _port_callback, _algorithm_callback]

    _iteration.iterate_over_columns(dataframe, data, columns, callbacks)

    return data["references"]


def _create_overview_sheet(
    workbook, worksheet, references, statistics, energy_to_treatments_map
):
    summary_references, _ = _write_data_get_references(
        data_column_start="A",
        data_header="Summary Statistics",
        dataframe=statistics,
        worksheet=worksheet,
    )

    last_data_row_number = int(
        summary_references["energy"].split(":")[-1].split("$")[-1]
    )

    energies = natsort.natsorted(list(energy_to_treatments_map.keys()))

    figure_row = last_data_row_number + 3

    for energy in energies:
        figure_column = "A"
        worksheet.write(f"{figure_column}{figure_row}", energy)
        figure_row += 1

        treatments = natsort.natsorted(energy_to_treatments_map[energy])

        for treatment in treatments:
            refs_by_treatment = references[treatment]

            chart_transverse = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )
            chart_radial = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )

            for port, refs_by_port in refs_by_treatment.items():
                data_references = refs_by_port["PyMedPhys"]

                chart_transverse.add_series(
                    {
                        "name": port,
                        "categories": data_references["gantry"],
                        "values": data_references["diff_x"],
                    }
                )

                chart_radial.add_series(
                    {
                        "name": port,
                        "categories": data_references["gantry"],
                        "values": data_references["diff_y"],
                    }
                )

            chart_transverse.set_title({"name": f"{energy} | {treatment} | Transverse"})
            chart_transverse.set_x_axis({"name": "Gantry Angle (degrees)"})
            chart_transverse.set_y_axis({"name": "Field - BB (mm)"})

            chart_radial.set_title({"name": f"{energy} | {treatment} | Radial"})
            chart_radial.set_x_axis({"name": "Gantry Angle (degrees)"})
            chart_radial.set_y_axis({"name": "Field - BB (mm)"})

            # TODO: Insert summary statistics for each chart. Save summary stats
            # within a dictionary back in main, when calculated for each chart, and
            # then pull the results out here for printing beneath each plot.

            worksheet.insert_chart(f"{figure_column}{figure_row}", chart_radial)
            worksheet.insert_chart(
                f"{figure_column}{figure_row + FIGURE_CELL_HEIGHT}", chart_transverse
            )

            _, col = xlsxwriter.utility.xl_cell_to_rowcol(f"{figure_column}1")
            figure_column = xlsxwriter.utility.xl_col_to_name(col + FIGURE_CELL_WIDTH)

        figure_row += FIGURE_CELL_HEIGHT * 2


def _create_algorithms_chart_sheet(workbook, algorithm_worksheet, references):
    figure_row = 1

    for treatment, refs_by_treatment in references.items():
        for port, refs_by_port in refs_by_treatment.items():
            chart_transverse = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )
            chart_radial = workbook.add_chart(
                {"type": "scatter", "subtype": "straight"}
            )

            for algorithm, data_references in refs_by_port.items():
                chart_transverse.add_series(
                    {
                        "name": algorithm,
                        "categories": data_references["gantry"],
                        "values": data_references["diff_x"],
                    }
                )

                chart_radial.add_series(
                    {
                        "name": algorithm,
                        "categories": data_references["gantry"],
                        "values": data_references["diff_y"],
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
    data_header: Dict,
    dataframe: "pd.DataFrame",
    worksheet: "xlsxwriter.worksheet",
):
    top_left_cell = f"{data_column_start}1"

    if isinstance(data_header, str):
        data_header = {data_header: ""}
    header_rows = len(data_header.keys())

    _, col = xlsxwriter.utility.xl_cell_to_rowcol(top_left_cell)
    second_column_letter = xlsxwriter.utility.xl_col_to_name(col + 1)

    for i, (key, item) in enumerate(data_header.items()):
        worksheet.write(f"{data_column_start}{i+1}", key)
        worksheet.write(f"{second_column_letter}{i+1}", item)

    dataframe_header_row = header_rows + 2
    data_first_row_number = dataframe_header_row + 1

    columns = dataframe.columns
    last_row_number = len(dataframe) + dataframe_header_row
    last_col_letter_with_gap = xlsxwriter.utility.xl_col_to_name(col + len(columns) + 1)
    sheet_name = worksheet.name

    worksheet.write_row(f"{data_column_start}{dataframe_header_row}", dataframe.columns)

    references = {}
    for i, column in enumerate(columns):
        series = dataframe[column]
        column_letter = xlsxwriter.utility.xl_col_to_name(col + i)
        worksheet.write_column(f"{column_letter}{data_first_row_number}", series)

        references[
            column
        ] = f"='{sheet_name}'!${column_letter}${data_first_row_number}:${column_letter}${last_row_number}"

    return references, last_col_letter_with_gap


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
