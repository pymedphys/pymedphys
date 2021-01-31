from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql, pytest, sqlalchemy

import pymedphys.mosaiq


@pytest.mark.mosaiqdb
def test_mock_patient_table():
    msq_server = "."
    test_db_name = "MosaiqTest77008"

    sa_user = "sa"
    sa_password = "sqlServerPassw0rd"

    conn = pymssql.connect(msq_server, user=sa_user, password=sa_password)
    conn.autocommit(True)
    cursor = conn.cursor()
    cursor.execute(f"create database {test_db_name}")
    cursor.close()

    patient_df = pd.DataFrame(
        [("Larry", "Fine"), ("Moe", "Howard"), ("Curly", "Howard")],
        columns=["First_Name", "Last_Name"],
    )
    patient_df.index = patient_df.index + 10001  # use the index+10001 as the Pat_ID1

    ident_df = pd.DataFrame([("MR8001"), ("MR8002"), ("MR8003")], columns=["IDA"])
    ident_df.index = (
        ident_df.index + 10001
    )  # use index+10001 in the same order as Pat_ID1

    conn_str = f"mssql+pymssql://{sa_user}:{sa_password}@{msq_server}/{test_db_name}"
    engine = sqlalchemy.create_engine(conn_str, echo=False)

    patient_df.to_sql(
        "Patient", engine, if_exists="replace", index=True, index_label="Pat_Id1"
    )
    ident_df.to_sql(
        "Ident", engine, if_exists="replace", index=True, index_label="Pat_Id1"
    )

    connection = pymedphys.mosaiq.connect(
        msq_server,
        port=1433,
        database=test_db_name,
        username=sa_user,
        password=sa_password,
    )

    result_all = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT
            Pat_Id1,
            FirstName
        FROM Patient
        """,
    )

    for patient in result_all:
        pat_id1, first_name = patient[0], patient[1]
        print(f"Pat_ID1:{pat_id1}  First Name:{first_name}")

    assert len(result_all) == 3

    moe_patient_name = mosaiq.helpers.get_patient_name(connection, "MR8002")

    assert moe_patient_name == "Howard, Moe"
