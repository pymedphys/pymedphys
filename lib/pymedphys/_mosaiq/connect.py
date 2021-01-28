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

from pymedphys._imports import pymssql

from . import credentials as _credentials


def connect_with_credential(
    username: str,
    password: str,
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
) -> "pymssql.Connection":
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
    conn : pymssql.Connection
        The Connection object to the database.

    Raises
    ------
    WrongUsernameOrPassword
        If the wrong credentials are provided.

    """

    try:
        conn = pymssql.connect(
            hostname, username, password, database=database, port=port
        )
    except pymssql.OperationalError as error:
        error_message = error.args[0][1]
        if error_message.startswith(b"Login failed for user"):
            raise _credentials.WrongUsernameOrPassword("Wrong credentials") from error

        raise

    return conn
