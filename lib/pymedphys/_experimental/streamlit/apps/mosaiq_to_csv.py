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

import base64
import pathlib
from typing import Any, Dict, List, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import toml

import pymedphys
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as _mosaiq

CATEGORY = categories.PLANNING
TITLE = "Mosaiq to CSV"

LIB_ROOT = pathlib.Path(__file__).parents[3]
TEST_DATA_DIR = LIB_ROOT.joinpath("tests", "mosaiq", "data")

PASSWORD_REPLACE = b"\x00" * 15
FIRST_NAME_USERNAME_MAP = {
    "Simon": "dummyusername",
}

# Given dynamic SQL queries are created in the functions below the SQL
# query is sanitised by only allowing table names and column names to
# pull from the below.
ALLOWLIST_TABLE_NAMES = [
    "Ident",
    "Patient",
    "TxField",
    "TxFieldPoint",
    "Site",
    "TrackTreatment",
    "Staff",
    "Chklist",
    "QCLTask",
]

ALLOWLIST_COLUMN_NAMES = [
    "IDA",
    "Pat_ID1",
    "SIT_Set_ID",
    "FLD_ID",
    "Staff_ID",
    "TSK_ID",
]


def main():
    config = st_config.get_config()
    connection = _mosaiq.get_single_mosaiq_connection_with_config(config)

    comma_sep_patient_ids: str = st.text_input("Comma Separated Patient IDs")
    if comma_sep_patient_ids == "":
        st.stop()

    patient_ids = [item.strip() for item in comma_sep_patient_ids.split(",")]
    tables, types_map = _get_all_tables(connection, patient_ids)
    _apply_table_type_conversions_inplace(tables, types_map)

    _save_tables_to_tests_directory(tables, types_map)


def _get_all_tables(
    connection: pymedphys.mosaiq.Connection, patient_ids: List[str]
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict[str, str]]]:
    """Get Mosaiq tables that are relevant for PyMedPhys regression testing.

    Take a list of patient_ids and steps through the MSSQL Mosaiq
    database with the intent to extract the relevant rows from the
    relevant tables for PyMedPhys regression testing.


    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A connection object to the Mosaiq SQL server.
    patient_ids : List[str]
        The list of Patient IDs (MRNs) to use for extracting data from
        Mosaiq.

    Returns
    -------
    tables
        A dictionary of Pandas DataFrames with dictionary keys defined
        by the Mosaiq table name and the table contents being the Mosaiq
        rows that are relevant to the Patient IDs provided.

    types_map
        A dictionary of dictionaries that present the MSSQL column types
        of the tables.
    """
    tables: Dict[str, pd.DataFrame] = {}
    types_map: Dict[str, Dict[str, str]] = {}

    tables["Ident"] = get_filtered_table(
        connection, types_map, "Ident", "IDA", patient_ids
    )

    # Patient.Pat_ID1 = Ident.Pat_ID1
    pat_id1s = tables["Ident"]["Pat_Id1"].unique()
    tables["Patient"] = get_filtered_table(
        connection, types_map, "Patient", "Pat_ID1", pat_id1s
    )
    tables["TxField"] = get_filtered_table(
        connection, types_map, "TxField", "Pat_ID1", pat_id1s
    )

    # TxField.SIT_Set_ID = Site.SIT_Set_ID
    sit_set_ids = tables["TxField"]["SIT_Set_ID"].unique()
    tables["Site"] = get_filtered_table(
        connection, types_map, "Site", "SIT_Set_ID", sit_set_ids
    )

    # TrackTreatment.FLD_ID = TxField.FLD_ID
    fld_ids = tables["TxField"]["FLD_ID"].unique()
    tables["TrackTreatment"] = get_filtered_table(
        connection, types_map, "TrackTreatment", "FLD_ID", fld_ids
    )

    # Chklist.Pat_ID1 = Ident.Pat_ID1 AND
    # Patient.Pat_ID1 = Ident.Pat_ID1 AND
    # QCLTask.TSK_ID = Chklist.TSK_ID AND
    # Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
    tables["Chklist"] = get_filtered_table(
        connection, types_map, "Chklist", "Pat_ID1", pat_id1s
    )

    tsk_ids = tables["Chklist"]["TSK_ID"].unique()
    tables["QCLTask"] = get_filtered_table(
        connection, types_map, "QCLTask", "TSK_ID", tsk_ids
    )

    responsible_staff_ids = tables["Chklist"]["Rsp_Staff_ID"].unique()
    completed_staff_ids = tables["Chklist"]["Com_Staff_ID"].unique()
    machine_staff_ids = tables["TrackTreatment"]["Machine_ID_Staff_ID"].unique()
    staff_ids_with_nans = (
        set(responsible_staff_ids).union(completed_staff_ids).union(machine_staff_ids)
    )
    staff_ids = np.array(list(staff_ids_with_nans))
    staff_ids = staff_ids[np.logical_not(np.isnan(staff_ids))]
    staff_ids = staff_ids.astype(int)

    # Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID
    tables["Staff"] = get_filtered_table(
        connection, types_map, "Staff", "Staff_ID", staff_ids.tolist()
    )
    tables["Staff"]["PasswordBytes"] = tables["Staff"]["PasswordBytes"].apply(
        lambda x: PASSWORD_REPLACE
    )
    for index, row in tables["Staff"].iterrows():
        first_name = row["First_Name"]
        if first_name.strip() == "":
            continue

        new_username = FIRST_NAME_USERNAME_MAP[first_name]
        tables["Staff"].loc[index, "User_Name"] = new_username

    # TxFieldPoint.FLD_ID = %(field_id)s
    tables["TxFieldPoint"] = get_filtered_table(
        connection, types_map, "TxFieldPoint", "FLD_ID", fld_ids
    )

    return tables, types_map


def _apply_table_type_conversions_inplace(tables, types_map):
    """Convert binary types to b64 and make sure pandas defines datetime
    types even if a column has a None entry.

    Utilised for reliable saving and loading to and from a csv file.
    """
    for table_name, table in tables.items():
        column_types = types_map[table_name]
        for column_name, column_type in column_types.items():
            if column_type in ["binary", "timestamp"]:
                table[column_name] = table[column_name].apply(
                    lambda x: base64.b64encode(x).decode()
                )
                continue
            if column_type == "datetime":
                table[column_name] = table[column_name].apply(_convert_to_datetime)

        st.write(f"## `{table_name}` Table")
        st.write(table)


def _save_tables_to_tests_directory(tables, types_map):
    """Save the tables within the PyMedPhys testing directory."""
    if not st.button("Save tables within PyMedPhys mosaiq testing dir"):
        st.stop()

    for table_name, df in tables.items():
        filepath = TEST_DATA_DIR.joinpath(table_name).with_suffix(".csv")
        df.to_csv(filepath)

    toml_filepath = TEST_DATA_DIR.joinpath("types_map.toml")

    with open(toml_filepath, "w") as f:
        toml.dump(types_map, f)


def get_filtered_table(
    connection: pymedphys.mosaiq.Connection,
    types_map: Dict[str, Dict[str, str]],
    table: str,
    column_name: str,
    column_values: List[Any],
) -> "pd.DataFrame":
    """Step through a set of provided column values extracting these
    from the MSSQL database.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
    types_map : Dict[str, Dict[str, str]]
        The types_map to append to the new column schema to
    table : str
        The table name to pull data from
    column_name : str
        The column name to pull data from
    column_values : List[Any]
        The values to match against within the columns

    Returns
    -------
    df : pd.DataFrame
    """
    column_names, column_types = _get_all_columns(connection, table)
    df = pd.DataFrame(data=[], columns=column_names)
    for column_value in column_values:
        df = _append_filtered_table(connection, df, table, column_name, column_value)

    types_map[table] = dict(zip(column_names, column_types))

    return df


def _append_filtered_table(connection, df, table, column_name, column_value):
    """Append the rows from an MSSQL table where the column_value
    matches within the given column_name.
    """
    df = pd.concat(
        [df, _get_filtered_table(connection, table, column_name, column_value)],
        ignore_index=True,
    )
    return df


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def _get_all_columns(connection, table):
    """Get the column schema from an MSSQL table."""
    raw_columns = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = %(table)s
        """,
        {
            "table": table,
        },
    )

    columns = [item[0] for item in raw_columns]
    types = [item[1] for item in raw_columns]

    return columns, types


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def _get_filtered_table(connection, table, column_name, column_value):
    """Get the rows from an MSSQL table where the column_value matches
    within the given column_name."""
    if not table in ALLOWLIST_TABLE_NAMES:
        raise ValueError(f"{table} must be within the allowlist")

    if not column_name in ALLOWLIST_COLUMN_NAMES:
        raise ValueError(f"{column_name} must be within the allowlist")

    column_value = str(column_value)
    column_names, _ = _get_all_columns(connection, table)

    sql_string = f"""
        SELECT *
        FROM {table}
        WHERE {table}.{column_name} = %(column_value)s
        """

    raw_results = pymedphys.mosaiq.execute(
        connection,
        sql_string,
        {
            "table": table,
            "column_name": column_name,
            "column_value": column_value,
        },
    )

    df = pd.DataFrame(raw_results, columns=column_names)

    return df


def _convert_to_datetime(item):
    if item is not None:
        return pd.to_datetime(item)

    return item
