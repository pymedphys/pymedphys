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
from typing import Any, Dict, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd  # pylint: disable = unused-import

from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc

from . import _dbf


def expand_border_events(mask):
    shifted_right = np.concatenate([[False], mask])
    shifted_left = np.concatenate([mask, [False]])

    combined = np.logical_or(shifted_right, shifted_left)

    return combined


def get_directories_and_initial_database(
    config: Dict[str, Any],
    refresh_cache: bool,
    return_site=False,
) -> Tuple[
    pathlib.Path,
    pathlib.Path,
    "pd.DataFrame",
    "pd.Timestamp",
    Dict[str, Dict[str, str]],
]:
    """Load up paths from configuration, and pull in the primary
    database structure before further filtering.

    Requests the user to select a site, a date, and a machine id
    and then returns an initial database table for these selections
    as well as the relevant directories.

    Parameters
    ----------
    config : Dict[str, Any]
    refresh_cache : bool
        Whether or not to utilise the streamlit cache, or to pull
        directly from the database.

    Returns
    -------
    database_directory : pathlib.Path
        The directory of the iView database for the chosen site.
    icom_directory : pathlib.Path
        The directory of the iCom records for the chosen site.
    database_table : pandas.DataFrame
        An initial table for the iView database. The column definitions
        for this table can be found within
        ``pymedphys._experimental.streamlit.utilities.iview._dbf.load_and_merge_dbfs``.
    selected_date : pandas.Timestamp
        The date selected by the user.
    linac_to_directories_map : Dict[str, Dict[str, str]]
        A mapping from Linac name/ids through to the configuration
        directories for that Linac.
    """

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

    try:
        database_table["machine_id"] = database_table["machine_id"].apply(
            lambda x: alias_map[x]
        )
    except KeyError as e:
        raise ValueError(
            "Unable to map the iView machine ID to Linac ID. According "
            "to your config.toml file the following alias map was "
            f"created {alias_map}. {e} was not found within "
            "the iView machine names provided of "
            f"{set(alias_map.keys())}."
        ) from e

    # --

    selected_date = database_table["datetime"].dt.date.unique()
    if len(selected_date) != 1:
        raise ValueError("Expected only one date")

    selected_date = selected_date[0]

    # --

    linac_to_directories_map = {
        item["name"]: item["directories"] for item in linac_map[chosen_site]
    }

    if return_site:
        # This is a nasty hack.
        # TODO: Fix this.
        return (
            database_directory,  # type: ignore
            icom_directory,
            database_table,
            selected_date,
            linac_to_directories_map,
            chosen_site,
        )
    else:
        return (
            database_directory,
            icom_directory,
            database_table,
            selected_date,
            linac_to_directories_map,
        )


def _load_database_with_cache(database_directory, refresh_cache):
    merged = _dbf.load_and_merge_dbfs(database_directory, refresh_cache)

    return merged
