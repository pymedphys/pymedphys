from typing import Dict, Optional

from pymedphys._imports import pymssql  # pylint: disable = unused-import

from . import connect as _connect
from . import credentials as _credentials


def connect(
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
    alias: Optional[str] = None,
) -> "pymssql.Cursor":
    """Connect to a Mosaiq SQL server.

    The first time running this function on a system will result in a
    prompt to login to the Mosaiq SQL server. The provided credentials
    will be stored within the operating systems password storage
    facilities. Subsequent calls to this function will pull from that
    password storage in order to connect.

    Parameters
    ----------
    hostname : str
        The IP address or hostname of the SQL server.
    port : int, optional
        The port at which the SQL server is hosted, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"
    alias : Optional[str], optional
        A human readable representation of the server, this is the name
        of the server presented to the user should their not be
        credentials already on the machine, by default "hostname:port/database"

    Returns
    -------
    pymssql.Cursor
        A database cursor. This cursor can be passed to
        ``pymedphys.mosaiq.execute`` to be able to run queries.

    """
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
