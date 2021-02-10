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

from pymedphys._imports import numpy as np

from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc

from . import _dbf


def expand_border_events(mask):
    shifted_right = np.concatenate([[False], mask])
    shifted_left = np.concatenate([mask, [False]])

    combined = np.logical_or(shifted_right, shifted_left)

    return combined


def get_directories_and_initial_database(config, refresh_cache):
    site_directories = _config.get_site_directories(config)
    chosen_site = misc.site_picker(config, "Site")

    database_directory = site_directories[chosen_site]["iviewdb"]

    icom_directory = site_directories[chosen_site]["icom"]

    database_table = _load_database_with_cache(database_directory, refresh_cache)

    linac_map = {site["name"]: site["linac"] for site in config["site"]}

    alias_map = {}
    for linac in linac_map[chosen_site]:
        try:
            alias_map[linac["aliases"]["iview"]] = linac["name"]
        except KeyError:
            alias_map[linac["name"]] = linac["name"]

    database_table["machine_id"] = database_table["machine_id"].apply(
        lambda x: alias_map[x]
    )

    # --

    selected_date = database_table["datetime"].dt.date.unique()
    if len(selected_date) != 1:
        raise ValueError("Expected only one date")

    selected_date = selected_date[0]

    selected_machine_id = database_table["machine_id"].unique()
    if len(selected_machine_id) != 1:
        raise ValueError("Expected only one machine id")

    selected_machine_id = selected_machine_id[0]

    # --

    linac_to_directories_map = {
        item["name"]: item["directories"] for item in linac_map[chosen_site]
    }

    qa_directory = pathlib.Path(linac_to_directories_map[selected_machine_id]["qa"])

    return (
        database_directory,
        icom_directory,
        qa_directory,
        database_table,
        selected_date,
        selected_machine_id,
    )


def _load_database_with_cache(database_directory, refresh_cache):
    merged = _dbf.load_and_merge_dbfs(database_directory, refresh_cache)

    return merged
