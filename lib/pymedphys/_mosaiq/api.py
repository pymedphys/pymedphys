# Copyright (C) 2018, 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from typing import Dict, List, Optional, Tuple

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
    will be stored within the operating system's password storage
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
        of the server presented to the user should there not be
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


def execute(
    cursor: "pymssql.Cursor", query: str, parameters: Dict = None
) -> List[Tuple[str, ...]]:
    """Execute SQL queries on a Mosaiq database.

    Parameters
    ----------
    cursor : pymssql.Cursor
        A database cursor. This can be retrieved by calling
        ``pymedphys.mosaiq.connect``
    query : str
        The SQL query to execute. Do not parse Python variables directly
        into this string. Instead utilise create this string as if you
        are going to call ``format`` on it
        (https://docs.python.org/3/library/stdtypes.html#str.format)
        and then utilise the parameters optional argument to this
        function. That way, the underlying library ``pymssql`` will
        sanitise the parameters to protect against malicious inputs.
    parameters : Dict, optional
        Parameters to be included within the query. These are sanitised
        by the underlying ``pymssql`` library before being included
        within the query string, by default None

    Returns
    -------
    List[Tuple[str]]
        The results from the database query organised so that each row
        is an item within the returned list.

    Examples
    --------
    >>> import pymedphys.mosaiq
    >>> cursor = pymedphys.mosaiq.connect('msqsql')  # doctest: +SKIP

    >>> pymedphys.mosaiq.execute(
    ...     cursor,
    ...     '''
    ...     SELECT
    ...         Ident.IDA,
    ...         Patient.Last_Name,
    ...         Patient.First_Name
    ...     FROM Ident, Patient
    ...     WHERE
    ...         Patient.Pat_ID1 = Ident.Pat_ID1 AND
    ...         Patient.Last_Name = %(last_name)s
    ...     ''',
    ...     {"last_name": "PHANTOM"},
    ... )  # doctest: +SKIP
    [('654324', 'PHANTOM', 'CATPHAN'),
     ('944444', 'PHANTOM', 'DELTA4'),
     ('654321', 'PHANTOM', 'PELVIS'),
     ('012534', 'PHANTOM', 'QUASAR4D'),
     ('987654', 'PHANTOM', 'RESPIRATORY'),
     ('654325', 'PHANTOM', 'RW3')]
    """

    try:
        cursor.execute(query, parameters)
    except Exception:
        print("query:\n    {}\nparameters:\n    {}".format(query, parameters))
        raise

    data = []
    while True:
        row: Tuple[str, ...] = cursor.fetchone()
        if row is None:
            break

        data.append(row)

    return data
