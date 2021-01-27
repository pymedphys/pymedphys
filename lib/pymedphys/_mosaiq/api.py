from typing import Dict, Optional

from pymedphys._imports import pymssql  # pylint: disable = unused-import

from . import connect as _connect
from . import credentials as _credentials


def connect(
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
    alias: Optional[str] = None,
):
    username, password = _credentials.get_username_password_with_prompt_fallback(
        hostname=hostname, port=port, database=database, alias=alias
    )
    conn = _connect.connect_with_credential(
        username, password, hostname=hostname, port=port, database=database
    )
    cursor = conn.cursor()
    return cursor


def execute(cursor: "pymssql.Cursor", sql_string: str, parameters: Dict = None):
    """Executes a given SQL string on an SQL cursor."""

    try:
        cursor.execute(sql_string, parameters)
    except Exception:
        print("sql_string:\n    {}\nparameters:\n    {}".format(sql_string, parameters))
        raise

    data = []

    while True:
        row = cursor.fetchone()
        if row is None:
            break

        data.append(row)

    return data
