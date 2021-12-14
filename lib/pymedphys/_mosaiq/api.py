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

from . import connect as _connect
from . import credentials as _credentials

Connection = _connect.Connection
Cursor = _connect.Cursor


def connect(
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
    alias: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Connection:
    """Connect to a Mosaiq SQL server.

    The first time running this function on a system will result in a
    prompt to login to the Mosaiq SQL server. The provided credentials
    will be stored within the operating system's password storage
    facilities. Subsequent calls to this function will pull from that
    password storage in order to connect.

    Can optionally be called as a context manager. This will close the
    database connection once leaving the context manager.

    Parameters
    ----------
    hostname : str
        The IP address or hostname of the SQL server.
    port : int, optional
        The port at which the SQL server is hosted, by default ``1433``
    database : str, optional
        The MSSQL database name, by default ``"MOSAIQ"``
    alias : Optional[str], optional
        A human readable representation of the server, this is the name
        of the server presented to the user should there not be
        credentials already on the machine, by default ``"hostname:port/database"``
    username : Optional[str], optional
        Provide a username to login to the database with, by default the
        username is either pulled from the system's credential storage,
        or an interactive prompt is used.
    password : Optional[str], optional
        Provide a password to login to the database with, by default the
        password is either pulled from the system's credential storage,
        or an interactive prompt is used.

    Returns
    -------
    connection : pymedphys.mosaiq.Connection
        A database connection. This connection can be passed to
        :func:`pymedphys.mosaiq.execute` to be able to run queries.

        The method ``close()`` can be called on this object to close the
        database connection.

    Examples
    --------
    See :func:`pymedphys.mosaiq.execute` for examples of usage.

    """
    if username is None and password is None:
        username, password = _credentials.get_username_password_with_prompt_fallback(
            hostname=hostname, port=port, database=database, alias=alias
        )
    if username is None or password is None:
        raise ValueError(
            "Must either provide both username and password, or neither of them."
        )

    connection = _connect.connect_with_credentials(
        username, password, hostname=hostname, port=port, database=database
    )

    return connection


def execute(
    connection: Connection, query: str, parameters: Dict = None
) -> List[Tuple[str, ...]]:
    """Execute SQL queries on a Mosaiq database.

    Parameters
    ----------
    connection : pymedphys.mosaiq.Connection
        A database connection. This can be retrieved by calling
        ``pymedphys.mosaiq.connect``
    query : str
        The SQL query to execute. Do not parse Python variables directly
        into this string. Instead create this string as if you
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
    results : List[Tuple[str, ...]]
        The results from the database query organised so that each row
        is an item within the returned list.

    Examples
    --------
    Directly calling the connection object and listing all patients that
    have the last name of ``"PHANTOM"``.

    >>> import pymedphys.mosaiq
    >>> connection = pymedphys.mosaiq.connect('msqsql')  # doctest: +SKIP

    >>> pymedphys.mosaiq.execute(
    ...     connection,
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

    Connecting via a context manager and using pandas to present the
    results as a table.

    >>> import pandas as pd
    >>> import pymedphys.mosaiq

    >>> with pymedphys.mosaiq.connect('msqsql') as connection:  # doctest: +SKIP
    ...     results = pymedphys.mosaiq.execute(
    ...         connection,
    ...         '''
    ...         SELECT
    ...             Ident.IDA,
    ...             Chklist.Due_DtTm
    ...         FROM Chklist, Staff, Ident
    ...         WHERE
    ...             Chklist.Pat_ID1 = Ident.Pat_ID1 AND
    ...             Staff.Staff_ID = Chklist.Rsp_Staff_ID AND
    ...             Staff.Last_Name = %(qcl_location)s AND
    ...             Chklist.Complete = 0
    ...         ''',
    ...         {"qcl_location": "Physics_Check"},
    ...     )

    >>> pd.DataFrame(  # doctest: +SKIP
    ...     data=results,
    ...     columns=[
    ...         "patient_id",
    ...         "due",
    ...     ],
    ... )
      patient_id                 due
    0     000000 2021-02-01 23:59:59
    1     000001 2021-02-01 23:59:59
    2     000002 2021-02-01 23:59:59
    3     000003 2021-03-08 23:59:59
    """

    with connection.cursor() as cursor:
        cursor.execute(query=query, parameters=parameters)
        results: List[Tuple[str, ...]] = cursor.fetchall()

    return results
