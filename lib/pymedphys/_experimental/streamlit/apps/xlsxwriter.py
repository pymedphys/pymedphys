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

from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st
from pymedphys._imports import xlsxwriter

from pymedphys._experimental.streamlit.apps.wlutz import _utilities

HOME = pathlib.Path.home()
PYMEDPHYS_LIBRARY_ROOT = pathlib.Path(__file__).parents[3]
LOGO_PATH = PYMEDPHYS_LIBRARY_ROOT.joinpath("_streamlit", "pymedphys-title.png")


def main():
    st.title("Excel file creation sandbox")

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

    st.write("## Playing with Wlutz results")

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
        raw_results_dataframe = _get_results(raw_results_csv_path)
    except FileNotFoundError:
        st.error("Winston Lutz results not yet calculated/saved for this date.")
        st.stop()

    # st.write(raw_results_dataframe)

    filtered = raw_results_dataframe
    for column in ["treatment", "port", "algorithm"]:
        filtered = _filter_by_column(filtered, column)

    filtered = filtered.sort_values("seconds_since_midnight")

    st.write(filtered)

    wlutz_xlsx_filepath = wlutz_directory_by_date.joinpath("overview.xlsx")
    with xlsxwriter.Workbook(wlutz_xlsx_filepath) as workbook:
        overview_worksheet = workbook.add_worksheet(name="Overview")
        data_worksheet = workbook.add_worksheet(name="Data")

        references = _write_data_get_references(
            filtered[["gantry", "diff_x", "diff_y"]], data_worksheet
        )

        st.write(references)

        chart = workbook.add_chart({"type": "scatter"})
        chart.add_series(
            {
                "name": "Transverse",
                "categories": references["gantry"],
                "values": references["diff_x"],
            }
        )

        chart.add_series(
            {
                "name": "Radial",
                "categories": references["gantry"],
                "values": references["diff_y"],
            }
        )

        overview_worksheet.insert_chart("A1", chart)

    _insert_file_download_link(wlutz_xlsx_filepath)


def _create_chart(workbook, dataframe, title):
    chart = workbook.add_chart({"type": "scatter"})


def _write_data_get_references(
    dataframe: "pd.DataFrame", worksheet: "xlsxwriter.worksheet"
):
    columns = dataframe.columns
    worksheet.write_row("A1", dataframe.columns)
    last_row_number = len(dataframe) + 1
    sheet_name = worksheet.name

    references = {}
    for i, column in enumerate(columns):
        series = dataframe[column]
        column_letter = xlsxwriter.utility.xl_col_to_name(i)
        worksheet.write_column(f"{column_letter}2", series)

        references[
            column
        ] = f"={sheet_name}!${column_letter}$2:${column_letter}${last_row_number}"

    return references


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
