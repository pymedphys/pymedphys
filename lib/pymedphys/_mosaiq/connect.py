# Copyright (C) 2021 Derek Lane, Cancer Care Associates
# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""A toolbox for connecting to Mosaiq SQL.
"""

from typing import Dict, List, Tuple

from pymedphys._imports import pymssql

from . import credentials as _credentials


class Connection:
    """A Mosaiq DB Connection object.

    A wrapper around the ``pymssql.Connection`` object.
    """

    def __init__(
        self,
        username: str,
        password: str,
        hostname: str,
        port: int = 1433,
        database: str = "MOSAIQ",
    ):
        try:
            self._connection = pymssql.connect(
                hostname, username, password, database=database, port=port
            )
        except pymssql.OperationalError as error:
            error_message = error.args[0][1]

            if error_message.startswith(b"Login failed for user"):
                raise _credentials.WrongUsernameOrPassword(
                    "Wrong credentials"
                ) from error

            raise ValueError(
                f"When attempting to connect to {database}@{hostname}:{port} "
                f"with the {username} user a pymssql.OperationalError was "
                "raised"
            ) from error

    def cursor(self) -> "Cursor":
        return Cursor(self._connection)

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Cursor:
    """A Mosaiq DB Cursor object.

    A wrapper around the ``pymssql.Cursor`` object.
    """

    def __init__(self, connection: "pymssql.Connection"):
        self._cursor = connection.cursor()

    def close(self):
        self._cursor.close()

    def execute(self, query: str, parameters: Dict = None):
        self._cursor.execute(query, parameters)

    def fetchall(self) -> List[Tuple[str, ...]]:
        results: List[Tuple[str, ...]] = self._cursor.fetchall()

        return results

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def connect_with_credentials(
    username: str,
    password: str,
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
) -> Connection:
    """Connects to a Mosaiq database.

    Parameters
    ----------
    username : str
    password : str
    hostname : str
        The IP address or hostname of the SQL server.
    port : int, optional
        The port at which the SQL server is hosted, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"

    Returns
    -------
    connection : pymedphys.mosaiq.Connection
        A connection object to the database for execution.

    Raises
    ------
    WrongUsernameOrPassword
        If the wrong credentials are provided.

    """
    connection = Connection(
        username=username,
        password=password,
        hostname=hostname,
        port=port,
        database=database,
    )

    return connection
