from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql, pytest, sqlalchemy

from pymedphys._mosaiq.helpers import get_patient_fields, get_patient_name
from pymedphys.mosaiq import connect, execute

msq_server = "."
test_db_name = "MosaiqTest77008"

sa_user = "sa"
sa_password = "sqlServerPassw0rd"

# set up a SQLAlchemy engine to be used for populating tables
connection_str = f"mssql+pymssql://{sa_user}:{sa_password}@{msq_server}/{test_db_name}"
engine = sqlalchemy.create_engine(connection_str, echo=False)


def create_test_db():
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


@pytest.fixture(name="create_mock_patients")
def fixture_create_mock_patients():
    """ creates a mock patient, with small Patient and Ident tables with relevant attributes"""

    create_test_db()

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
    patient_ident_df.drop(columns=["IDA"]).to_sql(
        "Patient", engine, if_exists="replace", index=True, index_label="Pat_Id1"
    )
    patient_ident_df.drop(columns=["First_Name", "Last_Name"]).to_sql(
        "Ident", engine, if_exists="replace", index=True, index_label="Pat_Id1"
    )

    # return the combined dataframe, if need to be used for follow-on processing
    return patient_ident_df


@pytest.mark.mosaiqdb
def test_get_patient_name():
    """ tests the get_patient_name helper function"""

    with connect(
        msq_server,
        port=1433,
        database=test_db_name,
        username=sa_user,
        password=sa_password,
    ) as connection:

        # test a generic query for patient info
        result_all = execute(
            connection,
            """
            SELECT
                Pat_Id1,
                First_Name,
                Last_Name
            FROM Patient
            """,
        )

        # show us the patients
        for patient in result_all:
            pat_id1, first_name, last_name = patient
            print(f"Pat_ID1:{pat_id1}  First Name:{first_name}  Last Name:{last_name}")

        # and check that the correct number were created
        assert len(result_all) == 3

        # test the get_patient_name helper function
        moe_patient_name = get_patient_name(connection, "MR8002")

        # finally spot check Moe
        assert moe_patient_name == "HOWARD, Moe"


@pytest.mark.mosaiqdb
def test_get_patient_fields(create_mock_patients):
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    patient_ident_df = create_mock_patients

    # set up site to have same rows as patient_ident
    site_df = patient_ident_df.drop(columns=["First_Name", "Last_Name", "IDA"])
    site_df["Site_Name"] = "rx1"
    site_df["Pat_ID1"] = site_df.index
    site_df.index = np.arange(1, len(site_df) + 1)

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

    # now use SQLAlchemy to populate the two tables
    site_df.to_sql(
        "Site", engine, if_exists="replace", index=True, index_label="SIT_SET_ID"
    )
    txfield_df.to_sql(
        "TxField", engine, if_exists="replace", index=True, index_label="FLD_ID"
    )

    with connect(
        msq_server,
        port=1433,
        database=test_db_name,
        username=sa_user,
        password=sa_password,
    ) as connection:

        # test the get_patient_fields helper function
        txfield_df = get_patient_fields(connection, "MR8002")
        print(txfield_df)

        # make sure the correct number of rows were returned
        assert len(txfield_df) == 3

        # for each treatment field
        for fld_id, txfield in txfield_df.iterrows():
            print(fld_id, txfield)

            # check that the field label matches the field name
            assert f"Field{txfield['field_label']}" == txfield["field_name"]
