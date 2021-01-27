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

from contextlib import contextmanager
from getpass import getpass
from typing import Callable

from pymedphys._imports import keyring, pymssql

from . import credentials as _credentials
from . import utilities as _utilities


class WrongUsernameOrPassword(ValueError):
    pass


def connect_with_credential(
    hostname: str,
    username: str,
    password: str,
    database: str = "MOSAIQ",
    port: int = 1433,
) -> "pymssql.Connection":
    """Connects to a Mosaiq database.

    Parameters
    ----------
    hostname : str
        The hostname of the server.
    username : str
    password : str
    database : str, optional
    port : int, optional

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
            raise WrongUsernameOrPassword("Wrong credentials")

        raise

    return conn


def execute_sql(cursor, sql_string, parameters=None):
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


def single_connect(
    sql_server_and_port,
    user_input=input,
    password_input=getpass,
    output=print,
    database="MOSAIQ",
):
    """Connect to the Mosaiq server.
    Ask the user for a password if they haven't logged in before.
    """
    conn = _connect_with_credential_then_prompt_if_fail(
        sql_server_and_port,
        user_input=user_input,
        password_input=password_input,
        output=output,
        database=database,
    )

    return conn, conn.cursor()


def multi_connect(sql_server_and_ports, database="MOSAIQ"):
    """Create SQL connections and cursors."""
    connections = dict()
    cursors = dict()

    for server_port in sql_server_and_ports:
        connections[server_port], cursors[server_port] = single_connect(
            server_port, database=database
        )

    return connections, cursors


def single_close(connection):
    connection.close()


def multi_close(connections):
    """Close the SQL connections."""
    for _, item in connections.items():
        single_close(item)


@contextmanager
def connect(sql_server_and_ports, database="MOSAIQ"):
    """A controlled execution class that opens and closes multiple SQL
    connections.

    Usage example:
        import pymedphys

        with pymedphys.mosaiq.connect('msqsql') as cursor:
            do_something(cursor)
    """
    if isinstance(sql_server_and_ports, str):
        sql_server_and_ports_as_list = [sql_server_and_ports]
        return_unnested_cursor = True
    else:
        sql_server_and_ports_as_list = list(sql_server_and_ports)
        return_unnested_cursor = False

    connections, cursors = multi_connect(sql_server_and_ports_as_list, database)
    try:
        if return_unnested_cursor:
            cursors = cursors[sql_server_and_ports]
        yield cursors
    finally:
        multi_close(connections)


mosaiq_connect = connect
multi_mosaiq_connect = connect


def _connect_with_credential_then_prompt_if_fail(
    hostname,
    port: int = 1433,
    database: str = "MOSAIQ",
    user_input: Callable = input,
    password_input: Callable = getpass,
    output: Callable = print,
) -> "pymssql.Connection":
    """Connects to a Mosaiq database utilising credentials saved with
    the keyring library.

    Parameters
    ----------
    sql_server_and_port : str
        A server and port separated by a colon (:). Eg "localhost:8888".
    user_input : callable, optional
        A function which prompts the user for input and returns the
        server's username, by default the built-in ``input`` function.
    password_input : callable, optional
        A function which prompts the user for a password input and
        returns the password for the provided user, by default the
        standard library ``getpass.getpass`` function.
    output : callable, optional
        A function which displays responses to the user, by default the
        built-in ``print``.
    database : str
        name of the Mosaiq database to be connected

    Returns
    -------
    conn : pymssql.Connection
        The Connection object to the database.

    Note
    ----
    The optional callable parameters utilised by this function are
    designed so that they can be overridden by libraries such as
    Streamlit.

    """
    user, password = _credentials.get_username_password_with_prompt_fallback(
        hostname,
        port=port,
        database=database,
        user_input=user_input,
        password_input=password_input,
        output=output,
    )

    def _exception_debug_print():
        exception_debug_string = (
            f"User: {user}, Hostname: {hostname}, Port: {port}, Database: {database}"
        )
        output(exception_debug_string)

    try:
        conn = pymssql.connect(hostname, user, password, database=database, port=port)
    except pymssql.OperationalError as error:
        error_message = error.args[0][1]
        if error_message.startswith(b"Login failed for user"):
            output("Login failed, wiping the saved username and password.")

            try:
                _credentials.delete_credentials(
                    hostname=hostname,
                    port=port,
                    database=database,
                )
            except keyring.errors.PasswordDeleteError:
                pass

            output("Please try login again:")
            conn = _connect_with_credential_then_prompt_if_fail(
                hostname=hostname,
                port=port,
                database=database,
            )
        else:
            _exception_debug_print()
            raise

    except Exception as error:
        _exception_debug_print()
        raise

    return conn
