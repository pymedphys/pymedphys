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
from typing import Dict, List, cast

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._experimental.streamlit.utilities import dbf


def load_and_merge_dbfs(
    database_directory: pathlib.Path, refresh_cache: bool
) -> "pd.DataFrame":
    """Load the image sequence data for a user provided date. Merge in
    relevant information from the relevant DBF databases.

    The PATIMG.DBF database is loaded up and the user is asked to select
    a date from that database. Then for the image sequences taken on
    that date the PORT.DBF, TRTMNT.DBF, and PATIENT.DBF are
    loaded and merged into date filtered PATIMG based ``pd.DataFrame``
    using their corresponding DBID keys.

    The DBID keys used to merge the databases together are respectively
    PORT_DBID, TRT_DBID, and PAT_DBID.

    Parameters
    ----------
    database_directory
        The path to the iViewDB directory. This directory contains the
        DBF files discussed above.
    refresh_cache
        Whether or not to reload the database caches from disk.

    Returns
    -------
    table
        A ``pandas.DataFrame`` that contains the columns
        "machine_id", "patient_id", "treatment", "port", "datetime",
        "PIMG_DBID", and "DICOM_UID".

        machine_id : str
            A machine identifier as defined by ORG_DTL within the
            PATIMG database.
        patient_id : str
            A patient identifier as defined by the ID column within the
            PATIENT database.
        treatment : str
            The treatment identifier as defined by the ID column within
            the TRTMNT database.
        port : str
            A port identifier as defined by the ID column within the
            PORT database.
        datetime : datetime.datetime
            The datetime representation of the image sequence start.
            Converted from the combination of both the IMG_DATE and
            IMG_TIME columns within the PATIMG database.
        PIMG_DBID : int
            The DBID column from the PATIMG database.
        DICOM_UID : str
            The DICOM_UID column from the PATIMG database.

    Notes
    -----
    If this has been run before for this given path, and
    ``refresh_cache=False``, the cached result
    for each database will be provided. The cache can be reset from the
    DBF files by passing ``refresh_cache=True``

    """
    patimg = load_iview_dbf(database_directory, refresh_cache, "patimg")

    dates = pd.to_datetime(patimg["IMG_DATE"], format="%Y%m%d").dt.date
    date_options = dates.sort_values(ascending=False).unique()

    selected_date = st.selectbox("Date", options=date_options)
    patimg_filtered_by_date = patimg.loc[dates == selected_date]

    merged = patimg_filtered_by_date

    for database_key, merge_key in [
        ("port", "PORT_DBID"),
        ("trtmnt", "TRT_DBID"),
        ("patient", "PAT_DBID"),
    ]:
        dbf_to_be_merged = load_iview_dbf(
            database_directory, refresh_cache, database_key
        )
        merged = merged.merge(dbf_to_be_merged, left_on=merge_key, right_on=merge_key)

    timestamps_string = (
        merged["IMG_DATE"].astype("str")
        + "T"
        + merged["IMG_TIME"].astype("str")
        + "000"
    )

    merged["datetime"] = pd.to_datetime(timestamps_string, format="%Y%m%dT%H%M%S%f")

    table = merged[
        [
            "machine_id",
            "patient_id",
            "treatment",
            "port",
            "datetime",
            "PIMG_DBID",
            "DICOM_UID",
            "LAST_NAME",
            "FIRST_NAME",
        ]
    ]

    return table


def load_iview_dbf(
    database_directory: pathlib.Path, refresh_cache: bool, config_key: str
) -> "pd.DataFrame":
    """Load iViewDB files with table specific column name mutation.

    Loads and manipulates column names of iView DBF database files.
    The column manipulation are designed so as to simplify the
    subsequent merging of these tables with pd.DataFrame.merge()

    The particular column manipulations undergone are defined within
    ``_DBF_DATABASE_LOADING_CONFIG``.

    Parameters
    ----------
    path
        The path to the iViewDB directory. This directory contains the
        iView DBF files.
    refresh_cache
        Whether or not to reload the cache from disk.
    config_key
        The particular database to load up. Options are "frame",
        "patimg", "port", "trtmnt", and "patient".

    Returns
    -------
    table
        A pandas DataFrame with columns defined by the combination of
        the "columns_to_keep" and "column_rename_map" parameters defined
        within ``_DBF_DATABASE_LOADING_CONFIG``.

    Notes
    -----
    If this has been run before for this given path, and
    ``refresh_cache=False``, the cached result
    will be provided without loading from the DBF database. The cache
    can be overridden by passing ``refresh_cache=True``

    """

    current_config = _DBF_DATABASE_LOADING_CONFIG[config_key]
    filename = cast(str, current_config["filename"])
    columns_to_keep = cast(List[str], current_config["columns_to_keep"])
    column_rename_map = cast(Dict[str, str], current_config["column_rename_map"])

    table = _load_dbf_base(
        database_directory, refresh_cache, filename, columns_to_keep, column_rename_map
    )
    return table


_DBF_DATABASE_LOADING_CONFIG = {
    "frame": {
        "filename": "FRAME.dbf",
        "columns_to_keep": ["DBID", "PIMG_DBID", "DELTA_MS"],
        "column_rename_map": {"DBID": "FRAME_DBID"},
    },
    "patimg": {
        "filename": "PATIMG.dbf",
        "columns_to_keep": [
            "DBID",
            "DICOM_UID",
            "IMG_DATE",
            "IMG_TIME",
            "PORT_DBID",
            "ORG_DTL",
        ],
        "column_rename_map": {
            # These are renamed so that when a pd.DataFrame.merge()
            # function is undergone the PIMG_DBID columns in both
            # database have the same name
            "DBID": "PIMG_DBID",
            "ORG_DTL": "machine_id",
        },
    },
    "port": {
        "filename": "PORT.dbf",
        "columns_to_keep": ["DBID", "TRT_DBID", "ID"],
        # ID is renamed here so that when pd.DataFrame.merge() is
        # undergone the ID columns between the databases don't clash
        "column_rename_map": {"DBID": "PORT_DBID", "ID": "port"},
    },
    "trtmnt": {
        "filename": "TRTMNT.dbf",
        "columns_to_keep": ["DBID", "PAT_DBID", "ID"],
        "column_rename_map": {"DBID": "TRT_DBID", "ID": "treatment"},
    },
    "patient": {
        "filename": "PATIENT.dbf",
        "columns_to_keep": ["DBID", "ID", "LAST_NAME", "FIRST_NAME"],
        "column_rename_map": {"DBID": "PAT_DBID", "ID": "patient_id"},
    },
}


def _dbf_to_pandas_without_cache(path: pathlib.Path) -> "pd.DataFrame":
    return pd.DataFrame(iter(dbf.get_dbf_table(path)))


@st.cache(allow_output_mutation=True)
def _dbf_to_pandas_with_cache(path: pathlib.Path) -> "List[pd.DataFrame]":
    """Streamlit cached dbf read.

    Notes
    -----
    Returns a mutable list so that the cache can be updated inplace.

    """
    return [_dbf_to_pandas_without_cache(path)]


# TODO: Consider replacing the `refresh_cache` logic with a watchdog
# driven event model. See
# <https://github.com/pymedphys/pymedphys/pull/1143#discussion_r520242368>
# for details.
def _dbf_to_pandas(path: pathlib.Path, refresh_cache=True) -> "pd.DataFrame":
    """Retrieves the pandas.DataFrame representation of a DBF database.

    Parameters
    ----------
    path
        The full DBF database path to load.
    refresh_cache
        Whether or not to reload the cache from disk.

    Notes
    -----
    If this has been run before for this given path, and
    ``refresh_cache=False``, the cached result
    will be provided without loading from the DBF database. The cache
    can be overridden by passing ``refresh_cache=True``

    """
    result = _dbf_to_pandas_with_cache(path)

    if refresh_cache:
        result[0] = _dbf_to_pandas_without_cache(path)

    return result[0]


def _load_dbf_base(
    database_directory: pathlib.Path,
    refresh_cache: bool,
    filename: str,
    columns_to_keep: List[str],
    column_rename_map: Dict[str, str],
) -> "pd.DataFrame":
    dbf_path = database_directory.joinpath(filename)
    table = _dbf_to_pandas(dbf_path, refresh_cache)[columns_to_keep]
    table = table.rename(column_rename_map, axis="columns")

    return table
