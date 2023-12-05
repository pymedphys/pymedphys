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


from pymedphys._imports import altair as alt
from pymedphys._imports import natsort
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import streamlit_ace, tomlkit

from pymedphys._experimental.streamlit.utilities import iteration as _iteration
from pymedphys._experimental.streamlit.utilities.iview import ui as iview_ui

from . import _calculation, _config, _corrections, _excel


def main():
    """The entrance function for the WLutz Arc Streamlit GUI.

    This GUI connects to an iViewDB stored on a shared network drive
    and allows users to plot the difference between the field centre
    and the ball bearing centre accross a range of gantry angles.

    """
    (
        bb_diameter,
        penumbra,
        advanced_mode,
        demo_mode,
        loosen_internal_tolerances,
    ) = _set_parameters()
    config = _config.get_config(demo_mode)

    if demo_mode and advanced_mode:
        st.write("## Demo Configuration")
        config = tomlkit.loads(
            streamlit_ace.st_ace(value=tomlkit.dumps(config), language="toml")
        )

    (
        database_table,
        database_directory,
        qa_directory,
        selected_date,
    ) = iview_ui.iview_and_icom_filter_and_align(config, advanced_mode)

    wlutz_directory = qa_directory.joinpath("Winston-Lutz Results")
    wlutz_directory_by_date = wlutz_directory.joinpath(
        selected_date.strftime("%Y-%m-%d")
    )

    if advanced_mode:
        st.write(
            f"""
                ## Directory where results are being saved

                `{wlutz_directory_by_date}`
            """
        )

    _calculation.calculations_ui(
        database_table,
        database_directory,
        wlutz_directory_by_date,
        bb_diameter,
        penumbra,
        advanced_mode,
        loosen_internal_tolerances,
    )

    st.write("---")

    _presentation_of_results(wlutz_directory_by_date, advanced_mode)


def _presentation_of_results(wlutz_directory_by_date, advanced_mode):
    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")
    wlutz_xlsx_filepath = wlutz_directory_by_date.joinpath("overview.xlsx")

    try:
        calculated_results = pd.read_csv(raw_results_csv_path, index_col=False)
    except FileNotFoundError:
        return

    st.write(
        f"""
        ## Overview of results already calculated

        Here are the results loaded from the CSV file saved at:

            {raw_results_csv_path.resolve()}

        As calculations are undergone using the above they are added to
        this file, which is then loaded to produce the following collated
        plots and Excel overview file. The Excel overview file location
        is saved at:

            {wlutz_xlsx_filepath.resolve()}

        You can also download that file by using the link at the bottom
        of this page.

        ---
        """
    )

    dataframe = calculated_results.sort_values("seconds_since_midnight")
    dataframe_by_algorithm = _iteration.filter_by(dataframe, "algorithm", "PyMedPhys")

    statistics = _overview_statistics(dataframe_by_algorithm)
    st.write(statistics)

    _overview_figures(dataframe_by_algorithm)
    _excel.write_excel_overview(dataframe, statistics, wlutz_xlsx_filepath)

    if advanced_mode:
        st.write("### Experimental iCom and collimator corrections")

        experimental_collimator_corrections = st.checkbox(
            "Turn on experimental collimator and iCom correction statistics?"
        )
        if experimental_collimator_corrections:
            st.write("#### Statistics")

            (
                dataframe_with_corrections,
                collimator_correction,
            ) = _corrections.apply_corrections(dataframe_by_algorithm)

            dataframe_with_corrections["diff_x"] = dataframe_with_corrections[
                "diff_x_coll_corrected"
            ]
            dataframe_with_corrections["diff_y"] = dataframe_with_corrections[
                "diff_y_coll_corrected"
            ]

            statistics_with_corrections = _overview_statistics(
                dataframe_with_corrections
            )
            st.write(statistics_with_corrections)

            st.write("#### Predicted Collimator Rotation Correction")
            st.write(
                f"""
                    * Shift in MLC travel direction =
                    `{round(collimator_correction[0], 2)}` mm
                    * Shift in Jaw travel direction =
                    `{round(collimator_correction[1], 2)}` mm
                """
            )


def _overview_figures(dataframe):
    def _energy_callback(_dataframe, _data, energy):
        st.write(f"### {energy}")

    def _treatment_callback(dataframe, _data, energy, treatment):
        st.write(f"#### {treatment}")

        for title, column, axis in [
            ("Radial", "diff_y", "y-axis"),
            ("Transverse", "diff_x", "x-axis"),
        ]:
            altair_chart = (
                alt.Chart(dataframe)
                .mark_line(point=True)
                .encode(
                    x=alt.X("gantry", axis=alt.Axis(title="Gantry")),
                    y=alt.Y(
                        column, axis=alt.Axis(title=f"iView {axis} (mm) [Field - BB]")
                    ),
                    color=alt.Color("port", legend=alt.Legend(title="Port")),
                    tooltip=[
                        "time",
                        "port",
                        "diff_x",
                        "diff_y",
                        "gantry",
                        "collimator",
                        "turn_table",
                        "filename",
                    ],
                )
            ).properties(title=f"{title} | {energy} | {treatment}")

            st.altair_chart(altair_chart, use_container_width=True)
            st.write(_overview_statistics(dataframe, directions=(column,)))

    _iteration.iterate_over_columns(
        dataframe,
        data=None,
        columns=["energy", "treatment"],
        callbacks=[_energy_callback, _treatment_callback],
    )


def _overview_statistics(dataframe, directions=("diff_y", "diff_x")):
    statistics = []
    energies = dataframe["energy"].unique()
    energies = natsort.natsorted(energies)

    column_direction_map = {"diff_x": "Transverse", "diff_y": "Radial"}
    for energy in energies:
        dataframe_by_energy = _iteration.filter_by(dataframe, "energy", energy)

        for column in directions:
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
    return statistics


def _set_parameters():
    st.sidebar.write("# Configuration")

    try:
        _config.get_config(False)
        demo_mode = st.sidebar.checkbox("Demo Mode", value=False)
    except FileNotFoundError:
        demo_mode = True

    advanced_mode = st.sidebar.checkbox("Advanced Mode", value=False)

    st.sidebar.write("---")

    st.sidebar.write("# Daily QA (vs Monthly QA)")

    loosen_internal_tolerances = st.sidebar.checkbox(
        "Loosen algorithm tolerances for Daily QA air cavity detection", False
    )

    st.sidebar.write("---")

    st.sidebar.write("# Parameters")

    if loosen_internal_tolerances:
        default_bb_diameter = 12.0
    else:
        default_bb_diameter = 8.0

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", value=default_bb_diameter)
    penumbra = st.sidebar.number_input("Penumbra (mm)", value=2.0)

    return bb_diameter, penumbra, advanced_mode, demo_mode, loosen_internal_tolerances
