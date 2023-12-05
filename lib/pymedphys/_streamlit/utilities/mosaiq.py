# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Dict, Optional

from pymedphys._imports import streamlit as st
from typing_extensions import Literal

from pymedphys._mosaiq import connect as _connect
from pymedphys._mosaiq import credentials as _credentials


def get_single_mosaiq_connection_with_config(config):
    valid_site_config = {}
    for site_config in config["site"]:
        try:
            site_name = site_config["name"]
            mosaiq_config = site_config["mosaiq"]
            hostname = mosaiq_config["hostname"]
        except KeyError:
            continue

        try:
            port = mosaiq_config["port"]
        except KeyError:
            port = 1433

        try:
            alias = mosaiq_config["alias"]
        except KeyError:
            alias = None

        valid_site_config[site_name] = {
            "hostname": hostname,
            "port": port,
            "alias": alias,
        }

    site_options = list(valid_site_config.keys())
    if len(site_options) == 0:
        raise ValueError("No valid site options within your config file.")

    if len(site_options) == 1:
        chosen_site = site_options[0]
    else:
        chosen_site = st.radio("Site", site_options)

    chosen_site_config = valid_site_config[chosen_site]
    connection = get_cached_mosaiq_connection(chosen_site_config["hostname"])

    return connection


def get_uncached_mosaiq_connection(
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
    alias: Optional[str] = None,
) -> _connect.Connection:
    """Get the Mosaiq SQL database connection.

    User is prompted using the streamlit interface if needed credentials
    do not exist.

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
    connection : pymedphys.mosaiq.connection
        The Mosaiq SQL database connection.

    """
    if alias is None:
        alias = _credentials.get_keyring_storage_name(
            hostname=hostname, port=port, database=database
        )

    username, password = _credentials.get_username_and_password_without_prompt_fallback(
        hostname=hostname, port=port, database=database
    )

    if password:
        try:
            connection = _connect.connect_with_credentials(
                username, password, hostname=hostname, port=port, database=database
            )
            return connection
        except _credentials.WrongUsernameOrPassword as e:
            st.write(e)

    st.write("## Login to Mosaiq SQL Database")

    if not username:
        username = ""

    username = st.text_input(
        label=f"Username for the SQL server on {alias}",
        value=username,
        key=f"MosaiqSQLUsername_{alias}",
    )

    if username:
        _credentials.save_username(
            username, hostname=hostname, port=port, database=database
        )

    if not password:
        password = ""

    password = st.text_input(
        label="Password",
        value=password,
        type="password",
        key=f"MosaiqSQLPassword_{alias}",
    )

    if password:
        _credentials.save_password(
            password, hostname=hostname, port=port, database=database
        )

    if st.button("Connect"):
        st.experimental_rerun()

    st.stop()

    raise ValueError("This should never be reached")


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_cached_mosaiq_connection(
    hostname: str, port: int = 1433, database: str = "MOSAIQ", alias=None
) -> _connect.Connection:
    """A streamlit cached version of ``get_uncached_mosaiq_connection``.

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
    connection : pymedphys.mosaiq.Connection
        The Mosaiq SQL connection for the database.
    """
    return get_uncached_mosaiq_connection(
        hostname=hostname, port=port, database=database, alias=alias
    )


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_cached_mosaiq_connection_in_dict(
    hostname: str, port: int = 1433, database: str = "MOSAIQ", alias=None
) -> Dict[Literal["connection"], _connect.Connection]:
    """A streamlit cached version of ``get_uncached_mosaiq_connection`` with mutable output.

    This is designed so that the cached connection can be mutated as needed
    within the calling code.

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
    Dict["connection", pymedphys.mosaiq.Connection]
        A dictionary containing the Mosaiq SQL connection for the database.

    """
    return {
        "connection": get_uncached_mosaiq_connection(
            hostname=hostname, port=port, database=database, alias=alias
        )
    }
