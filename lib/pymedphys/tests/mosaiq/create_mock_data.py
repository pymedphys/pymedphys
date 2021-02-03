# create mock patients
from decimal import Decimal
from struct import pack

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql, pytest, sqlalchemy
from sqlalchemy.types import LargeBinary, Numeric

from pymedphys._mosaiq.helpers import get_patient_fields, get_patient_name
from pymedphys.mosaiq import connect, execute

msq_server = "."
test_db_name = "MosaiqTest77008"

sa_user = "sa"
sa_password = "sqlServerPassw0rd"


def dataframe_to_sql(df, tablename, index_label, dtype=None):
    """using a pd.DataFrame, populate a table in the configured database

    Parameters:
    df (pd.DataFrame):
        the dataframe with named columns to be used for populating the table
    tablename (str):
        the name of the table to populate
    index_label (str):
        the column name to be used for the primary key, which is the df index
    dtype (dict or None):
        optional dictionary of sqlalchemy types for the columns

    """

    connection_str = (
        f"mssql+pymssql://{sa_user}:{sa_password}@{msq_server}/{test_db_name}"
    )
    engine = sqlalchemy.create_engine(connection_str, echo=False)

    # now SQLAlchemy to populate table
    df.to_sql(
        tablename,
        engine,
        if_exists="replace",
        index=True,
        index_label=index_label,
        dtype=dtype,
    )

    # now get rid of the engine, to close it's connections
    engine.dispose()


def check_create_test_db():
    """ will create the test database, if it does not already exist on the instance """

    # sa connection to create the test database
    with pymssql.connect(
        msq_server, user=sa_user, password=sa_password
    ) as sql_sa_connection:

        sql_sa_connection.autocommit(True)

        # create the test db
        with sql_sa_connection.cursor() as cursor:
            cursor.execute(
                f"""
                IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{test_db_name}')
                BEGIN
                    CREATE DATABASE {test_db_name};
                END
                """
            )


def create_mock_patients():
    """ create some mock patients and populate the Patient and Ident tables """

    # create a single dataframe combining the Patient and Ident tables
    patient_ident_df = pd.DataFrame(
        [
            ("Larry", "Fine", "MR8001"),
            ("Moe", "Howard", "MR8002"),
            ("Curly", "Howard", "MR8003"),
        ],
        columns=["First_Name", "Last_Name", "IDA"],
    )

    # use the index+10001 as the Pat_ID1
    patient_ident_df.index = patient_ident_df.index + 10001

    # now SQLAlchemy to populate the two tables from the single composite
    dataframe_to_sql(
        patient_ident_df.drop(columns=["IDA"]),
        "Patient",
        index_label="Pat_Id1",
    )
    dataframe_to_sql(
        patient_ident_df.drop(columns=["First_Name", "Last_Name"]),
        "Ident",
        index_label="Pat_Id1",
    )

    # return the combined dataframe, if need to be used for follow-on processing
    return patient_ident_df


def create_mock_treatment_sites(patient_ident_df=None):
    """create mock treatment sites for the patient dataframe passed in
    or call create_mock_patients if None is passed"""

    if patient_ident_df is None:
        patient_ident_df = create_mock_patients()

    # set up site to have same rows as patient_ident
    site_df = patient_ident_df.drop(columns=["First_Name", "Last_Name", "IDA"])
    site_df["Site_Name"] = "rx1"
    site_df["Pat_ID1"] = site_df.index
    site_df.index = np.arange(1, len(site_df) + 1)
    site_df["SIT_SET_ID"] = site_df.index

    # now use SQLAlchemy to populate the two tables
    dataframe_to_sql(site_df, "Site", index_label="SIT_ID")

    return site_df


def create_mock_treatment_fields(site_df=None):
    """create mock treatment sites for the site dataframe passed in
    or call create_mock_treatment_sites if None is passed"""

    if site_df is None:
        site_df = create_mock_treatment_sites()

    # populate a list of tx_fields, 3 for each site
    tx_fields = []
    for sit_set_id, site in site_df.iterrows():
        tx_fields += [
            ("A", "FieldA", 1, "MU", 1, site["Pat_ID1"], sit_set_id),
            ("B", "FieldB", 1, "MU", 1, site["Pat_ID1"], sit_set_id),
            ("C", "FieldC", 1, "MU", 1, site["Pat_ID1"], sit_set_id),
        ]

    # now create the tx_field dataframe
    txfield_df = pd.DataFrame(
        tx_fields,
        columns=[
            "Field_Label",
            "Field_Name",
            "Version",
            "Meterset",
            "Type_Enum",
            "Pat_ID1",
            "SIT_SET_ID",
        ],
    )
    txfield_df.index += 1

    dataframe_to_sql(txfield_df, "TxField", index_label="FLD_ID")

    txfieldpoints = []
    for fld_id, _ in txfield_df.iterrows():
        txfieldpoints += [
            (
                fld_id,
                0,
                0.0,
                pack("hhl", 1, 2, 3),
                pack("hhl", 1, 2, 3),
                90.0,
                0.0,
                2.6,
                4.2,
            ),
            (
                fld_id,
                1,
                0.1,
                pack("hhl", 1, 2, 3),
                pack("hhl", 1, 2, 3),
                180.0,
                90.0,
                0.0,
                4.2,
            ),
            (
                fld_id,
                2,
                0.7,
                pack("hhl", 1, 2, 3),
                pack("hhl", 1, 2, 3),
                270.0,
                180.0,
                0.0,
                4.2,
            ),
            (
                fld_id,
                3,
                1.0,
                pack("hhl", 1, 2, 3),
                pack("hhl", 1, 2, 3),
                0.0,
                270.0,
                0.0,
                4.2,
            ),
        ]

    txfieldpoints_df = pd.DataFrame(
        txfieldpoints,
        columns=[
            "FLD_ID",
            "Point",
            "Index",
            "A_Leaf_Set",
            "B_Leaf_Set",
            "Gantry_Ang",
            "Coll_Ang",
            "Coll_Y1",
            "Coll_Y2",
        ],
    )
    txfieldpoints_df.index += 1

    dataframe_to_sql(
        txfieldpoints_df,
        "TxFieldPoint",
        index_label="TFP_ID",
        dtype={
            "Index": Numeric(precision=9, scale=3),
            "A_Leaf_Set": LargeBinary(length=200),
            "B_Leaf_Set": LargeBinary(length=200),
            "Gantry_Ang": Numeric(precision=4, scale=1),
            "Coll_Ang": Numeric(precision=4, scale=1),
            "Coll_Y1": Numeric(precision=4, scale=1),
            "Coll_Y2": Numeric(precision=4, scale=1),
        },
    )

    return txfield_df
