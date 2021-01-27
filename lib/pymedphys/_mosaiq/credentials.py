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

import functools
from getpass import getpass
from typing import Callable, Optional

from pymedphys._imports import keyring

KEYRING_SCOPE = "PyMedPhys_SQLLogin_Mosaiq"
USERNAME_KEY = "username"
PASSWORD_KEY = "password"


class WrongUsernameOrPassword(ValueError):
    pass


def get_username_and_password_without_prompt_fallback(
    hostname: str, port=1433, database="MOSAIQ"
):
    """Get username and password from keyring storage.

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"

    Returns
    -------
    username, password

    """

    username = get_username(hostname=hostname, port=port, database=database)
    password = get_password(hostname=hostname, port=port, database=database)

    return username, password


def get_username(hostname: str, port: int = 1433, database: str = "MOSAIQ"):
    """Get username from keyring storage

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"

    Returns
    -------
    username

    """
    storage_name = get_keyring_storage_name(
        hostname=hostname, port=port, database=database
    )
    username = keyring.get_password(storage_name, USERNAME_KEY)
    return username


def get_password(hostname: str, port: int = 1433, database: str = "MOSAIQ"):
    """Get password from keyring storage

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"

    Returns
    -------
    password
    """
    storage_name = get_keyring_storage_name(
        hostname=hostname, port=port, database=database
    )
    password = keyring.get_password(storage_name, PASSWORD_KEY)
    return password


def get_username_password_with_prompt_fallback(
    hostname,
    port: int = 1433,
    database: str = "MOSAIQ",
    user_input: Callable = input,
    password_input: Callable = getpass,
    output: Callable = print,
    alias: Optional[str] = None,
):
    """Get the username and password from the keyring storage.

    This will fallback to prompting the user for a username and password
    if one is not found. These credentials will then be subsequently
    stored.

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"
    user_input : Callable, optional
        A function by which to get an plain text input from the user,
        by default ``input``
    password_input : Callable, optional
        A function by which to get an password input from the user,
        by default ``getpass``
    output : Callable, optional
        A function by which to give feedback to the user, by default
        ``print``
    alias : Optional[str], optional
        A human readable representation of the server, this is the name
        of the server presented to the user should their not be
        credentials already on the machine, by default "hostname:port/database"

    Returns
    -------
    username, password

    Raises
    ------
    ValueError
        When a blank username is provided.
    """

    if alias is None:
        alias = get_keyring_storage_name(
            hostname=hostname, port=port, database=database
        )

    username, password = get_username_and_password_without_prompt_fallback(
        hostname=hostname, port=port, database=database
    )

    if username is None or username == "":
        output(f"Provide a user that only has `db_datareader` access to '{alias}'")
        username = user_input()
        if username == "":
            error_message = "Username should not be blank."
            output(error_message)
            raise ValueError(error_message)

        save_username(username, hostname=hostname, port=port, database=database)

    if password is None:
        output(f"Provide the password for the '{username}' user on '{alias}'")
        password = password_input()

        save_password(password, hostname=hostname, port=port, database=database)

    return username, password


def save_username(
    username: str, hostname: str, port: int = 1433, database: str = "MOSAIQ"
):
    """Save username within keyring storage.

    Parameters
    ----------
    username : str
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"
    """
    storage_name = get_keyring_storage_name(
        hostname=hostname, port=port, database=database
    )
    keyring.set_password(storage_name, USERNAME_KEY, username)


def save_password(
    password: str, hostname: str, port: int = 1433, database: str = "MOSAIQ"
):
    """Save password within keyring storage.

    Parameters
    ----------
    password : str
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"
    """
    storage_name = get_keyring_storage_name(
        hostname=hostname, port=port, database=database
    )
    keyring.set_password(storage_name, PASSWORD_KEY, password)


def delete_credentials(hostname: str, port: int = 1433, database: str = "MOSAIQ"):
    """Delete the credentials within keyring storage.

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"
    """
    storage_name = get_keyring_storage_name(
        hostname=hostname, port=port, database=database
    )
    keyring.delete_password(storage_name, USERNAME_KEY)
    keyring.delete_password(storage_name, PASSWORD_KEY)


@functools.lru_cache()
def get_keyring_storage_name(hostname, port=1433, database="MOSAIQ"):
    """Determines the keyring storage name to store SQL login credentials.

    Parameters
    ----------
    hostname : str
        The MSSQL server hostname
    port : int, optional
        The MSSQL server port, by default 1433
    database : str, optional
        The MSSQL database name, by default "MOSAIQ"

    Returns
    -------
    str
        The storage name to be used with keyring
    """
    return f"{KEYRING_SCOPE}_{hostname}:{port}/{database}"
