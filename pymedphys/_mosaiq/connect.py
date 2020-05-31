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

from pymedphys._imports import keyring, pymssql


def execute_sql(cursor, sql_string, parameters=None):
    """Executes a given SQL string on an SQL cursor.
    """
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


def get_username_password(storage_name):

    user = keyring.get_password("MosaiqSQL_username", storage_name)
    password = keyring.get_password("MosaiqSQL_password", storage_name)

    if user is None or user == "":
        print(
            "Provide a user that only has `db_datareader` access to the "
            "Mosaiq database at `{}`".format(storage_name)
        )
        user = input()
        if user == "":
            error_message = "Username should not be blank."
            print(error_message)
            raise ValueError(error_message)
        keyring.set_password("MosaiqSQL_username", storage_name, user)

    if password is None:
        print(
            "Provide password for '{}' server and '{}' user".format(storage_name, user)
        )
        password = getpass()
        keyring.set_password("MosaiqSQL_password", storage_name, password)

    return user, password


def separate_server_port_string(sql_server_and_port):
    split_tuple = str(sql_server_and_port).split(":")
    if len(split_tuple) == 1:
        server = split_tuple[0]
        port = 1433
    elif len(split_tuple) == 2:
        server, port = split_tuple
    else:
        raise ValueError(
            "Only one : should appear in server name,"
            " and it should be used to divide hostname from port number"
        )

    return server, port


def try_connect_delete_user_if_fail(sql_server_and_port):
    server, port = separate_server_port_string(sql_server_and_port)
    user, password = get_username_password(sql_server_and_port)

    try:
        conn = pymssql.connect(server, user, password, "MOSAIQ", port=port)
    except pymssql.OperationalError as error:
        error_message = error.args[0][1]
        if error_message.startswith(b"Login failed for user"):
            print("Login failed, wiping the saved username and password.")
            try:
                keyring.delete_password("MosaiqSQL_username", sql_server_and_port)
                keyring.delete_password("MosaiqSQL_password", sql_server_and_port)
            except keyring.errors.PasswordDeleteError as error:
                pass
            print("Please try login again:")
            conn = try_connect_delete_user_if_fail(sql_server_and_port)
        else:
            print(
                "Server Input: {}, User: {}, Hostname: {}, Port: {}".format(
                    sql_server_and_port, user, server, port
                )
            )
            raise

    except Exception as error:
        print(
            "Server Input: {}, User: {}, Hostname: {}, Port: {}".format(
                sql_server_and_port, user, server, port
            )
        )
        raise

    return conn


def single_connect(sql_server_and_port):
    """Connect to the Mosaiq server.
    Ask the user for a password if they haven't logged in before.
    """
    conn = try_connect_delete_user_if_fail(sql_server_and_port)

    return conn, conn.cursor()


def multi_connect(sql_server_and_ports):
    """Create SQL connections and cursors.
    """
    connections = dict()
    cursors = dict()

    for server_port in sql_server_and_ports:
        connections[server_port], cursors[server_port] = single_connect(server_port)

    return connections, cursors


def single_close(connection):
    connection.close()


def multi_close(connections):
    """Close the SQL connections.
    """
    for _, item in connections.items():
        single_close(item)


@contextmanager
def connect(sql_server_and_ports):
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

    connections, cursors = multi_connect(sql_server_and_ports_as_list)
    try:
        if return_unnested_cursor:
            cursors = cursors[sql_server_and_ports]
        yield cursors
    finally:
        multi_close(connections)


mosaiq_connect = connect
multi_mosaiq_connect = connect
