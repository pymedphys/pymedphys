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

import pathlib

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as _mosaiq

CATEGORY = categories.PLANNING
TITLE = "Mosaiq to CSV"

LIB_ROOT = pathlib.Path(__file__).parents[3]
TEST_DATA_DIR = LIB_ROOT.joinpath("tests", "mosaiq", "data")


ALLOWLIST_TABLE_NAMES = [
    "Ident",
    "Patient",
    "TxField",
    "TxFieldPoint",
    "Site",
    "TrackTreatment",
    "Staff",
]

ALLOWLIST_COLUMN_NAMES = [
    "IDA",
    "Pat_ID1",
    "SIT_Set_ID",
    "FLD_ID",
    "Staff_ID",
]


def main():
    config = st_config.get_config()
    connection = _mosaiq.get_single_mosaiq_connection_with_config(config)

    comma_sep_patient_ids: str = st.text_input("Comma Separated Patient IDs")
    if comma_sep_patient_ids == "":
        st.stop()

    patient_ids = [item.strip() for item in comma_sep_patient_ids.split(",")]

    tables = {}

    tables["Ident"] = get_filtered_table(connection, "Ident", "IDA", patient_ids)
    st.write("## `Ident` Table")
    st.write(tables["Ident"])

    # Patient.Pat_ID1 = Ident.Pat_ID1
    pat_id1s = tables["Ident"]["Pat_Id1"].unique()
    tables["Patient"] = get_filtered_table(connection, "Patient", "Pat_ID1", pat_id1s)
    tables["TxField"] = get_filtered_table(connection, "TxField", "Pat_ID1", pat_id1s)

    st.write("## `Patient` Table")
    st.write(tables["Patient"])

    st.write("## `TxField` Table")
    st.write(tables["TxField"])

    # TxField.SIT_Set_ID = Site.SIT_Set_ID
    sit_set_ids = tables["TxField"]["SIT_Set_ID"].unique()
    tables["Site"] = get_filtered_table(connection, "Site", "SIT_Set_ID", sit_set_ids)
    st.write("## `Site` Table")
    st.write(tables["Site"])

    # TrackTreatment.FLD_ID = TxField.FLD_ID
    fld_ids = tables["TxField"]["FLD_ID"].unique()
    tables["TrackTreatment"] = get_filtered_table(
        connection, "TrackTreatment", "FLD_ID", fld_ids
    )
    st.write("## `TrackTreatment` Table")
    st.write(tables["TrackTreatment"])
    machine_staff_ids = tables["TrackTreatment"]["Machine_ID_Staff_ID"].unique()

    # Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID
    tables["Staff"] = get_filtered_table(
        connection, "Staff", "Staff_ID", machine_staff_ids
    )

    st.write("## `Staff` Table")
    st.write(tables["Staff"])

    # TxFieldPoint.FLD_ID = %(field_id)s
    tables["TxFieldPoint"] = get_filtered_table(
        connection, "TxFieldPoint", "FLD_ID", fld_ids
    )
    st.write("## `TxFieldPoint` Table")
    st.write(tables["TxFieldPoint"])

    if not st.button("Save tables within PyMedPhys mosaiq testing dir"):
        st.stop()

    for table_name, df in tables.items():
        filepath = TEST_DATA_DIR.joinpath(table_name).with_suffix(".csv")
        df.to_csv(filepath)


def get_filtered_table(connection, table, column_name, column_values):
    df = pd.DataFrame()
    for column_value in column_values:
        df = _append_filtered_table(connection, df, table, column_name, column_value)

    return df


def _append_filtered_table(connection, df, table, column_name, column_value):
    df = pd.concat(
        [df, _get_filtered_table(connection, table, column_name, column_value)],
        ignore_index=True,
    )
    return df


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def _get_all_column_names(connection, table):
    raw_columns = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = %(table)s
        """,
        {
            "table": table,
        },
    )

    columns = [item[0] for item in raw_columns]

    return columns


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def _get_filtered_table(connection, table, column_name, column_value):
    if not table in ALLOWLIST_TABLE_NAMES:
        raise ValueError(f"{table} must be within the allowlist")

    if not column_name in ALLOWLIST_COLUMN_NAMES:
        raise ValueError(f"{column_name} must be within the allowlist")

    column_value = str(column_value)
    column_names = _get_all_column_names(connection, table)

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


# def _raw_delivery_data_sql(connection, field_id):
#     txfield_results = api.execute(
#         connection,
#         """
#         SELECT
#             TxField.Meterset,
#             TxField.RowVers
#         FROM TxField
#         WHERE
#             TxField.FLD_ID = %(field_id)s
#         """,
#         {
#             "field_id": field_id,
#         },
#     )

#     txfieldpoint_results = api.execute(
#         connection,
#         """
#         SELECT
#             TxFieldPoint.[Index],
#             TxFieldPoint.A_Leaf_Set,
#             TxFieldPoint.B_Leaf_Set,
#             TxFieldPoint.Gantry_Ang,
#             TxFieldPoint.Coll_Ang,
#             TxFieldPoint.Coll_Y1,
#             TxFieldPoint.Coll_Y2,
#             TxFieldPoint.RowVers
#         FROM TxFieldPoint
#         WHERE
#             TxFieldPoint.FLD_ID = %(field_id)s
#         ORDER BY
#             TxFieldPoint.Point
#         """,
#         {"field_id": field_id},
#     )

#     return txfield_results, txfieldpoint_results
