from pymedphys._imports import pymssql, pytest

from . import _connect


@pytest.mark.mosaiqdb
def test_can_we_db():
    conn = pymssql.connect(
        _connect.MSQ_SERVER, user=_connect.SA_USER, password=_connect.SA_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute("select * from sys.databases")

    # should print the four system databases
    databases = list(cursor)
    print(databases)

    # and check that the correct number are present
    assert len(databases) >= 4
