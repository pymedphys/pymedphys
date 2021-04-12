import contextlib

import pymedphys

MSQ_SERVER = "."
TEST_DB_NAME = "MosaiqTest77008"

SA_USER = "sa"
SA_PASSWORD = "sqlServerPassw0rd"


@contextlib.contextmanager
def connect():
    connection = pymedphys.mosaiq.connect(
        MSQ_SERVER,
        port=1433,
        database=TEST_DB_NAME,
        username=SA_USER,
        password=SA_PASSWORD,
    )

    try:
        yield connection
    finally:
        connection.close()
