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

    patient_df = pd.DataFrame([("Larry"), ("Moe"), ("Curly")], columns=["FirstName"])
    patient_df.index = patient_df.index + 10001  # use the index+10001 as the Pat_ID1

    conn_str = f"mssql+pymssql://{sa_user}:{sa_password}@{msq_server}/{test_db_name}"
    engine = sqlalchemy.create_engine(conn_str, echo=False)
    patient_df.to_sql(
        "Patient", engine, if_exists="replace", index=True, index_label="Pat_Id1"
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

    result_moe = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT
            Pat_Id1,
            FirstName
        FROM Patient
        WHERE Pat_Id1 = %(pat_id1)s
        """,
        {"pat_id1": 10002},
    )

    assert len(result_moe) == 1
    assert result_moe[0][0] == 10002
    assert result_moe[0][1] == "Moe"

    cursor.close()
