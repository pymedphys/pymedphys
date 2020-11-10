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

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._streamlit.utilities import dbf

DBF_DATABASE_LOADING_CONFIG = {
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
        "column_rename_map": {"DBID": "PIMG_DBID", "ORG_DTL": "machine_id"},
    },
    "port": {
        "filename": "PORT.dbf",
        "columns_to_keep": ["DBID", "TRT_DBID", "ID"],
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


def loading_and_merging_dbfs(database_directory, refresh_cache):
    patimg = load_dbf(database_directory, refresh_cache, "patimg")

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
        dbf_to_be_merged = load_dbf(database_directory, refresh_cache, database_key)
        merged = merged.merge(dbf_to_be_merged, left_on=merge_key, right_on=merge_key)

    timestamps_string = (
        merged["IMG_DATE"].astype("str")
        + "T"
        + merged["IMG_TIME"].astype("str")
        + "000"
    )

    merged["datetime"] = pd.to_datetime(timestamps_string, format="%Y%m%dT%H%M%S%f")
    merged["time"] = merged["datetime"].dt.time

    merged = merged[
        [
            "time",
            "machine_id",
            "patient_id",
            "treatment",
            "port",
            "datetime",
            "LAST_NAME",
            "FIRST_NAME",
            "PIMG_DBID",
            "DICOM_UID",
        ]
    ]

    return merged


def dbf_to_pandas_without_cache(path):
    return pd.DataFrame(iter(dbf.get_dbf_table(path)))


@st.cache()
def dbf_to_pandas_with_cache(path):
    return [dbf_to_pandas_without_cache(path)]


def dbf_to_pandas(path, refresh_cache=False):
    result = dbf_to_pandas_with_cache(path)

    if refresh_cache:
        result[0] = dbf_to_pandas_without_cache(path)

    return result[0]


def _load_dbf_base(
    database_directory, refresh_cache, filename, columns_to_keep, column_rename_map
):
    dbf_path = database_directory.joinpath(filename)
    table = dbf_to_pandas(dbf_path, refresh_cache)[columns_to_keep]
    table.rename(column_rename_map, axis="columns", inplace=True)

    return table


def load_dbf(database_directory, refresh_cache, config_key):
    table = _load_dbf_base(
        database_directory, refresh_cache, **DBF_DATABASE_LOADING_CONFIG[config_key]
    )
    return table
