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

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as _mosaiq

CATEGORY = categories.PLANNING
TITLE = "Mosaiq to CSV"


ALLOWLIST_TABLE_NAMES = [
    "TxField",
    "TxFieldPoint",
    "Ident",
    "Site",
    "TrackTreatment",
    "Patient",
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

    # relevant_tables = ALLOWLIST_TABLE_NAMES

    # columns = {}
    # for table_name in relevant_tables:
    #     columns[table_name] = get_all_column_names(connection, table_name)

    # st.write(columns)

    patient_id = st.text_input("Patient ID")

    ident = get_filtered_table(connection, "Ident", "IDA", patient_id)
    pat_id1 = str(ident["Pat_Id1"].iloc[0])
    st.write("## `Ident` Table")
    st.write(ident)

    # Patient.Pat_ID1 = Ident.Pat_ID1 AND

    patient = get_filtered_table(connection, "Patient", "Pat_ID1", pat_id1)
    st.write("## `Patient` Table")
    st.write(patient)

    tx_field = get_filtered_table(connection, "TxField", "Pat_ID1", pat_id1)
    st.write("## `TxField` Table")
    st.write(tx_field)

    # TxField.SIT_Set_ID = Site.SIT_Set_ID

    sit_set_ids = set()
    fld_ids = set()

    for _, tx_field_row in tx_field.iterrows():
        sit_set_ids.add(tx_field_row["SIT_Set_ID"])
        fld_ids.add(tx_field_row["FLD_ID"])

    site = pd.DataFrame()
    for sit_set_id in sit_set_ids:
        site = pd.concat(
            [site, get_filtered_table(connection, "Site", "SIT_Set_ID", sit_set_id)]
        )

    st.write("## `Site` Table")
    st.write(site)

    track_treatment = pd.DataFrame()
    for fld_id in fld_ids:
        # TrackTreatment.FLD_ID = TxField.FLD_ID

        track_treatment = pd.concat(
            [
                track_treatment,
                get_filtered_table(connection, "TrackTreatment", "FLD_ID", fld_id),
            ]
        )

    st.write("## `TrackTreatment` Table")
    st.write(track_treatment)
    machine_staff_ids = track_treatment["Machine_ID_Staff_ID"].unique()

    # Staff.Staff_ID = TrackTreatment.Machine_ID_Staff_ID

    staff = pd.DataFrame()
    for machine_staff_id in machine_staff_ids:

        staff = pd.concat(
            [
                staff,
                get_filtered_table(connection, "Staff", "Staff_ID", machine_staff_id),
            ]
        )

    st.write("## `Staff` Table")
    st.write(staff)

    # fields = helpers.get_patient_fields(connection, patient_id)
    # st.write(fields)

    # for _, field in fields.iterrows():
    #     field_id = field["field_id"]
    #     st.write(field_id)

    #     tx_field, tx_field_point = delivery.raw_delivery_data_sql(connection, field_id)
    #     st.write(tx_field)
    #     st.write(tx_field_point)


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def get_all_column_names(connection, table):
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
def get_filtered_table(connection, table, column_name, column_value):
    if not table in ALLOWLIST_TABLE_NAMES:
        raise ValueError(f"{table} must be within the allowlist")

    if not column_name in ALLOWLIST_COLUMN_NAMES:
        raise ValueError(f"{column_name} must be within the allowlist")

    column_value = str(column_value)
    column_names = get_all_column_names(connection, table)

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
