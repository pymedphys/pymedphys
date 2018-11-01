# Copyright (C) 2018 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""A toolbox for connecting to Mosaiq SQL.
"""

# import time
# import warnings
from getpass import getpass

import keyring
import pymssql


def execute_sql(cursor, sql_string, parameters=None):
    """Executes a given SQL string on an SQL cursor.
    """
    try:
        cursor.execute(sql_string, parameters)
    except Exception:
        print("sql_string:\n    {}\nparameters:\n    {}".format(
            sql_string, parameters
        ))
        raise

    data = []

    while True:
        row = cursor.fetchone()
        if row is None:
            break
        else:
            data.append(row)

    return data


def single_connect(server):
    """Connect to the Mosaiq server.
    Ask the user for a password if they haven't logged in before.
    """

    if type(server) is not str:
        raise TypeError("`server` input variable needs to be a string")

    user = keyring.get_password('MosaiqSQL_username', server)
    password = keyring.get_password('MosaiqSQL_password', server)

    if user is None:
        print(
            "Provide a user that only has `db_datareader` access to the "
            "Mosaiq database at `{}`".format(server)
        )
        user = input()
        keyring.set_password('MosaiqSQL_username', server, user)

    if password is None:
        print("Provide password for '{}' server and '{}' user".format(
            server, user))
        password = getpass()
        keyring.set_password('MosaiqSQL_password', server, password)

    try:
        conn = pymssql.connect(server, user, password, 'MOSAIQ')
    except Exception:
        print("Server: {}, User: {}".format(server, user))
        raise

    return conn, conn.cursor()


def multi_connect(sql_servers):
    """Create SQL connections and cursors.
    """
    connections = dict()
    cursors = dict()

    for server in sql_servers:
        connections[server], cursors[server] = single_connect(server)

    return connections, cursors


def single_close(connection):
    connection.close()


def multi_close(connections):
    """Close the SQL connections.
    """
    for _, item in connections.items():
        single_close(item)


class multi_mosaiq_connect():
    """A controlled execution class that opens and closes multiple SQL
    connections.

    Usage example:
        servers = ['nbccc-msq', 'msqsql']
        with multi_mosaiq_connect(users, servers) as cursors:
            do_something(cursors['nbccc-msq'])
            do_something(cursors['msqsql'])
    """

    def __init__(self, sql_servers):
        self.sql_servers = sql_servers

    def __enter__(self):
        self.connections, cursors = multi_connect(
            self.sql_servers)
        return cursors

    def __exit__(self, type, value, traceback):
        multi_close(self.connections)


class mosaiq_connect():
    """A controlled execution class that opens and closes a single SQL
    connection to mosaiq.

    Usage example:
        with mosaiq_connect('msqsql') as cursor:
            do_something(cursor)
    """

    def __init__(self, sql_server):
        self.sql_server = sql_server

    def __enter__(self):
        self.connection, cursor = single_connect(
            self.sql_server)
        return cursor

    def __exit__(self, type, value, traceback):
        single_close(self.connection)
