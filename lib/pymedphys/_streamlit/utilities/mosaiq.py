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

import pathlib
from typing import Any, Dict, Optional, Tuple

from pymedphys._imports import streamlit as st
from pymedphys._imports import toml
from typing_extensions import Literal

from pymedphys._config import get_config_dir
from pymedphys._mosaiq import connect as _connect
from pymedphys._mosaiq import credentials as _credentials

from . import config as st_config

DEFAULT_PORT = 1433
DEFAULT_DATABASE = "MOSAIQ"


def get_valid_mosaiq_sites_from_config(
    config: Dict,
) -> Dict[str, Dict[str, Any]]:
    """Extract valid Mosaiq site configurations from the config.

    Parameters
    ----------
    config : Dict
        The PyMedPhys configuration dictionary.

    Returns
    -------
    Dict[str, Dict[str, Any]]
        A dictionary mapping site names to their Mosaiq configuration
        (hostname, port, alias).
    """
    valid_sites = {}

    for site_config in config.get("site", []):
        try:
            site_name = site_config["name"]
            mosaiq_config = site_config["mosaiq"]
            hostname = mosaiq_config["hostname"]
        except KeyError:
            continue

        port = mosaiq_config.get("port", DEFAULT_PORT)
        alias = mosaiq_config.get("alias")

        valid_sites[site_name] = {
            "hostname": hostname,
            "port": port,
            "alias": alias,
        }

    return valid_sites


def prompt_for_mosaiq_connection() -> Tuple[str, int, str, str]:
    """Prompt the user to enter Mosaiq connection details via Streamlit UI.

    Returns
    -------
    Tuple[str, int, str, str]
        A tuple of (hostname, port, database, site_name).
    """
    st.write("## Mosaiq Database Connection Setup")
    st.write(
        "No Mosaiq database configuration found. "
        "Please enter your connection details below."
    )

    site_name = st.text_input(
        "Site Name",
        value="my-site",
        help="A friendly name for this site configuration.",
    )

    hostname = st.text_input(
        "SQL Server Hostname",
        help="The IP address or hostname of the Mosaiq SQL server.",
    )

    port = st.number_input(
        "SQL Server Port",
        value=DEFAULT_PORT,
        min_value=1,
        max_value=65535,
        help="The port number for the SQL server (default: 1433).",
    )

    database = st.text_input(
        "Database Name",
        value=DEFAULT_DATABASE,
        help="The name of the Mosaiq database (default: MOSAIQ).",
    )

    return hostname, int(port), database, site_name


def save_mosaiq_config_to_file(
    site_name: str,
    hostname: str,
    port: int = DEFAULT_PORT,
    database: str = DEFAULT_DATABASE,
) -> pathlib.Path:
    """Save Mosaiq connection configuration to the config.toml file.

    Parameters
    ----------
    site_name : str
        The friendly name for this site.
    hostname : str
        The SQL server hostname.
    port : int, optional
        The SQL server port, by default 1433.
    database : str, optional
        The database name, by default "MOSAIQ".

    Returns
    -------
    pathlib.Path
        The path to the config file that was updated.
    """
    config_dir = get_config_dir()
    config_path = config_dir / "config.toml"

    # Load existing config or create new one
    if config_path.exists():
        with open(config_path) as f:
            config = toml.load(f)
    else:
        config = {"version": 0}

    # Ensure 'site' key exists as a list
    if "site" not in config:
        config["site"] = []

    # Check if site already exists and update it, or add new site
    site_exists = False
    for site_config in config["site"]:
        if site_config.get("name") == site_name:
            # Update existing site
            if "mosaiq" not in site_config:
                site_config["mosaiq"] = {}
            site_config["mosaiq"]["hostname"] = hostname
            site_config["mosaiq"]["port"] = port
            site_config["mosaiq"]["alias"] = f"{site_name} Mosaiq SQL Server"
            site_exists = True
            break

    if not site_exists:
        # Add new site configuration
        new_site = {
            "name": site_name,
            "mosaiq": {
                "hostname": hostname,
                "port": port,
                "alias": f"{site_name} Mosaiq SQL Server",
            },
        }
        config["site"].append(new_site)

    # Write the updated config back to file
    with open(config_path, "w") as f:
        toml.dump(config, f)

    return config_path


def get_mosaiq_connection_with_prompts() -> _connect.Connection:
    """Get a Mosaiq database connection, prompting for config if needed.

    This function checks for existing Mosaiq configuration. If none exists,
    it prompts the user to enter connection details and optionally saves
    them to the config file.

    Returns
    -------
    pymedphys.mosaiq.Connection
        A connection object to the Mosaiq database.
    """
    # Try to load existing config
    try:
        config = st_config.get_config()
    except FileNotFoundError:
        config = {}

    valid_sites = get_valid_mosaiq_sites_from_config(config)

    if valid_sites:
        # Use existing configuration
        return get_single_mosaiq_connection_with_config(config)

    # No valid config found, prompt user for connection details
    hostname, port, database, site_name = prompt_for_mosaiq_connection()

    if not hostname:
        st.warning("Please enter a hostname to continue.")
        st.stop()

    # Option to save configuration
    col1, col2 = st.columns(2)

    with col1:
        save_config = st.checkbox(
            "Save connection details to config file",
            value=True,
            help="Save these settings to ~/.pymedphys/config.toml for future use.",
        )

    with col2:
        connect_button = st.button("Connect", type="primary")

    if not connect_button:
        st.stop()

    # Save config if requested
    if save_config:
        config_path = save_mosaiq_config_to_file(
            site_name=site_name,
            hostname=hostname,
            port=port,
            database=database,
        )
        st.success(f"Configuration saved to {config_path}")

    # Now get the connection using the streamlit mosaiq utility
    # which will prompt for credentials if needed
    return get_uncached_mosaiq_connection(
        hostname=hostname,
        port=port,
        database=database,
        alias=f"{site_name} Mosaiq SQL Server",
    )


def get_single_mosaiq_connection_with_config(config):
    valid_site_config = {}
    for site_config in config["site"]:
        try:
            site_name = site_config["name"]
            mosaiq_config = site_config["mosaiq"]
            hostname = mosaiq_config["hostname"]
            database = mosaiq_config.get("database", DEFAULT_DATABASE)
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
            "database": database,
        }

    site_options = list(valid_site_config.keys())
    if len(site_options) == 0:
        raise ValueError("No valid site options within your config file.")

    if len(site_options) == 1:
        chosen_site = site_options[0]
    else:
        chosen_site = st.radio("Site", site_options)

    chosen_site_config = valid_site_config[chosen_site]
    connection = get_cached_mosaiq_connection(
        chosen_site_config["hostname"],
        chosen_site_config["port"],
        chosen_site_config["database"],
        chosen_site_config["alias"],
    )

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
        st.rerun()

    st.stop()
    raise RuntimeError("unreachable")  # pylint: disable=unreachable  # st.stop() always raises StopException


@st.cache_resource()
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


@st.cache_resource()
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
