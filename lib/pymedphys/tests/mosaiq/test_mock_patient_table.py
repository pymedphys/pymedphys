from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql, pytest, sqlalchemy

from pymedphys._mosaiq.helpers import get_patient_name
from pymedphys.mosaiq import connect, execute


@pytest.mark.mosaiqdb
def test_mock_patient_table():
    msq_server = "."
    test_db_name = "MosaiqTest77008"

    sa_user = "sa"
    sa_password = "sqlServerPassw0rd"

    # sa connection to create/drop the test database
    sql_sa_connection = pymssql.connect(msq_server, user=sa_user, password=sa_password)
    sql_sa_connection.autocommit(True)

    try:
        # create the test db
        cursor = sql_sa_connection.cursor()
        cursor.execute(
            f"""
            IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{test_db_name}')
            BEGIN
                CREATE DATABASE {test_db_name};
            END
            """
        )
        cursor.close()

        # create dataframes for the Patient and Ident tables
        patient_df = pd.DataFrame(
            [("Larry", "Fine"), ("Moe", "Howard"), ("Curly", "Howard")],
            columns=["First_Name", "Last_Name"],
        )
        patient_df.index = (
            patient_df.index + 10001
        )  # use the index+10001 as the Pat_ID1

        ident_df = pd.DataFrame([("MR8001"), ("MR8002"), ("MR8003")], columns=["IDA"])
        ident_df.index = (
            ident_df.index + 10001
        )  # use index+10001 in the same order as Pat_ID1

        # now use SQLAlchemy to populate the two tables
        conn_str = (
            f"mssql+pymssql://{sa_user}:{sa_password}@{msq_server}/{test_db_name}"
        )
        engine = sqlalchemy.create_engine(conn_str, echo=False)

        patient_df.to_sql(
            "Patient", engine, if_exists="replace", index=True, index_label="Pat_Id1"
        )
        ident_df.to_sql(
            "Ident", engine, if_exists="replace", index=True, index_label="Pat_Id1"
        )

        # test a generic query for patient info
        connection = connect(
            msq_server,
            port=1433,
            database=test_db_name,
            username=sa_user,
            password=sa_password,
        )

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

        for patient in result_all:
            pat_id1, first_name, last_name = patient[0], patient[1], patient[2]
            print(f"Pat_ID1:{pat_id1}  First Name:{first_name}  Last Name:{last_name}")

        assert len(result_all) == 3

        # test the get_patient_name helper function
        moe_patient_name = get_patient_name(connection, "MR8002")

        assert moe_patient_name == "HOWARD, Moe"

    finally:
        # close the pymedphys connection
        if connection:
            connection.close()

        # clean up!
        if sql_sa_connection:
            sql_sa_connection.close()
