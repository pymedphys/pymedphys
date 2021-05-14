# Copyright (C) 2021 Cancer Care Associates

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
import functools
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.streamlit.utilities import icom as _icom
from pymedphys._experimental.streamlit.utilities.iview import _angles as iview_angles
from pymedphys._experimental.streamlit.utilities.iview import _sync as iview_sync
from pymedphys._experimental.streamlit.utilities.iview import (
    _utilities as iview_utilities,
)
from pymedphys._experimental.streamlit.utilities.iview import ui as iview_ui

from .wlutz import _calculation, _config

CATEGORY = categories.PLANNING
TITLE = "Daily WLutz"

# The tolerance for any given images absolute deviation of
# field_centre - bb_centre.
PROJECTION_TOLERANCE = 2.0  # mm

# The tolerance for the mean displacement of a given beam across all
# gantry angles.
MEAN_TOLERANCE = 1.0  # mm

SIMPLE = True

WARNING_BACKGROUND_COLOUR = "#fef4d5"
WARNING_FONT_COLOUR = "#947c2d"

ERROR_BACKGROUND_COLOUR = "#ffd5d5"
ERROR_FONT_COLOUR = "#9d292d"

SUCCESS_BACKGROUND_COLOUR = "#ceeed8"
SUCCESS_FONT_COLOUR = "#176c36"


def main():
    with pd.option_context("precision", 1):
        _ui()


def _ui():
    penumbra = 2
    advanced_mode = False
    loosen_internal_tolerances = True

    config = _config.get_config(False)

    (
        tables_per_machine,
        database_directory,
        qa_directories_per_machine,
        selected_date,
        chosen_site,
    ) = _custom_iview_icom_filter(config, advanced_mode)

    site_configurations = {
        site_config["name"]: site_config for site_config in config["site"]
    }
    site_to_linac_config_map = {
        site: site_config["linac"] for site, site_config in site_configurations.items()
    }
    all_linac_config_for_site = site_to_linac_config_map[chosen_site]
    expected_linacs = [
        linac_config["name"] for linac_config in all_linac_config_for_site
    ]
    expected_linac_energies = {
        linac_config["name"]: linac_config["energies"]
        for linac_config in all_linac_config_for_site
    }

    try:
        bb_diameter = site_configurations[chosen_site]["daily-wlutz"]["bb_diameter"]
    except KeyError:
        bb_diameter = 12

    if not st.button("Calculate"):
        st.stop()

    for machine_id in expected_linacs:
        st.write(f"## Calculations for `{machine_id}`")
        try:
            database_table = tables_per_machine[machine_id]
        except KeyError:
            st.warning(f"No images found for `{machine_id}`")
            continue

        for energy in expected_linac_energies[machine_id]:
            st.write(f"### Energy: `{energy}`")

            energy_masked = database_table.loc[database_table["energy"] == energy]
            if len(energy_masked) == 0:
                st.warning(f"No images found for `{energy}` on `{machine_id}`")
                continue

            qa_directory = qa_directories_per_machine[machine_id]

            wlutz_directory = qa_directory.joinpath("Winston-Lutz Results")
            wlutz_directory_by_date = wlutz_directory.joinpath(
                selected_date.strftime("%Y-%m-%d")
            )

            statistics_collection = _calculation.calculations_ui(
                database_table,
                database_directory,
                wlutz_directory_by_date,
                bb_diameter,
                penumbra,
                advanced_mode,
                loosen_internal_tolerances,
                quiet=True,
            )

            statistics_collection = statistics_collection.drop(
                ["algorithm", "treatment", "port", "energy"], axis=1
            )

            statistics_collection = pd.DataFrame(statistics_collection)

            statistics_collection = statistics_collection.rename(
                columns={
                    "orientation": "Direction",
                    "min": "Min (mm)",
                    "max": "Max (mm)",
                    "mean": "Mean (mm)",
                }
            )

            statistics_collection = statistics_collection.set_index(["Direction"])
            statistics_collection = statistics_collection.sort_index()

            styled_dataframe = statistics_collection.style.apply(
                _highlight_projection_tol, subset=["Min (mm)", "Max (mm)"]
            )
            styled_dataframe = styled_dataframe.apply(
                _highlight_mean_tol, subset=["Mean (mm)"]
            )

            st.dataframe(styled_dataframe)


def _base_tol_colouring(tolerance, val):
    return [
        f"background-color: {ERROR_BACKGROUND_COLOUR}; color: {ERROR_FONT_COLOUR}"
        if np.abs(v) > tolerance
        else f"background-color: {SUCCESS_BACKGROUND_COLOUR}; color: {SUCCESS_FONT_COLOUR}"
        for v in val
    ]


_highlight_projection_tol = functools.partial(_base_tol_colouring, PROJECTION_TOLERANCE)
_highlight_mean_tol = functools.partial(_base_tol_colouring, MEAN_TOLERANCE)


def _custom_iview_icom_filter(config, advanced_mode):
    refresh_cache = True
    quiet = True

    (
        database_directory,
        icom_directory,
        database_table,
        selected_date,
        linac_to_directories_map,
        chosen_site,
    ) = iview_utilities.get_directories_and_initial_database(
        config, refresh_cache, return_site=True
    )

    icom_patients_directory = icom_directory.joinpath("patients")

    database_table = iview_ui.get_user_image_set_selection(
        database_table, advanced_mode, quiet=quiet
    )
    database_table = iview_ui.load_image_frame_database(
        database_directory, database_table, refresh_cache, advanced_mode
    )

    machine_ids = database_table["machine_id"].unique()
    tables_per_machine = {}
    qa_directories_per_machine = {}
    for machine_id in machine_ids:
        filtered = database_table.loc[database_table["machine_id"] == machine_id]

        tables_per_machine[machine_id] = _icom_per_machine_id(
            filtered,
            machine_id,
            icom_patients_directory,
            selected_date,
            advanced_mode,
            quiet,
        )

        qa_directories_per_machine[machine_id] = pathlib.Path(
            linac_to_directories_map[machine_id]["qa"]
        )

    return (
        tables_per_machine,
        database_directory,
        qa_directories_per_machine,
        selected_date,
        chosen_site,
    )


def _icom_per_machine_id(
    database_table,
    selected_machine_id,
    icom_patients_directory,
    selected_date,
    advanced_mode,
    quiet,
):
    filepaths_to_load, offset_to_apply = iview_sync.icom_iview_timestamp_alignment(
        database_table,
        icom_patients_directory,
        selected_date,
        selected_machine_id,
        advanced_mode,
        quiet=quiet,
    )

    icom_datasets = []
    for filepath in filepaths_to_load:
        icom_dataframe = _icom.get_icom_dataset(filepath)
        icom_datasets.append(icom_dataframe.copy())

    icom_datasets = pd.concat(icom_datasets, axis=0, ignore_index=True)
    icom_datasets = icom_datasets.sort_values(by="datetime", inplace=False)

    icom_datasets["datetime"] = icom_datasets["datetime"] + datetime.timedelta(
        seconds=offset_to_apply
    )
    icom_datasets["time"] = icom_datasets["datetime"].dt.round("ms").dt.time

    icom_datasets = iview_angles.make_icom_angles_continuous(icom_datasets, quiet=quiet)

    midnight = (
        icom_datasets["datetime"]
        .iloc[0]
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    icom_datasets["seconds_since_midnight"] = (
        icom_datasets["datetime"] - midnight
    ).dt.total_seconds()
    database_table["seconds_since_midnight"] = (
        database_table["datetime"] - midnight
    ).dt.total_seconds()

    for lower, upper, centre, diameter in (
        ("x_lower", "x_upper", "centre_x", "width"),
        ("y_lower", "y_upper", "centre_y", "length"),
    ):
        (
            icom_datasets[lower],
            icom_datasets[upper],
        ) = iview_ui.get_bounds_from_centre_and_diameter(
            icom_datasets[centre], icom_datasets[diameter]
        )

    for column in [
        "gantry",
        "collimator",
        "turn_table",
        "x_lower",
        "x_upper",
        "y_lower",
        "y_upper",
    ]:
        iview_ui.table_transfer_via_interpolation(icom_datasets, database_table, column)

    icom_seconds = icom_datasets["seconds_since_midnight"]
    iview_seconds = database_table["seconds_since_midnight"]

    alignment_indices = np.argmin(
        np.abs(icom_seconds.values[None, :] - iview_seconds.values[:, None]), axis=1
    )

    energies = icom_datasets["energy"].values[alignment_indices]
    database_table["energy"] = energies

    database_table["width"] = database_table["x_upper"] - database_table["x_lower"]
    database_table["length"] = database_table["y_upper"] - database_table["y_lower"]

    return database_table
