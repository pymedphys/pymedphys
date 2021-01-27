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

from typing import Optional

from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import connect as _connect
from pymedphys._mosaiq import credentials as _credentials


def get_uncached_mosaiq_cursor(
    hostname: str,
    port: int = 1433,
    database: str = "MOSAIQ",
    alias: Optional[str] = None,
):
    """Get the Mosaiq SQL cursor. Prompt user for username and password if needed.

    Parameters
    ----------
    server : str
        The hostname and optionally the port, separated by a colon (:).
        The following are all valid options:

            * msqsql
            * msqsql:1433
            * 127.0.0.1:8888

    Returns
    -------
    cursor : pymssql.Cursor
        The Mosaiq SQL cursor for the connection.

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
            conn = _connect.connect_with_credential(
                username, password, hostname=hostname, port=port, database=database
            )
            cursor = conn.cursor()
            return cursor
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

    return  # This is okay that is unreachable, it's just there to make pylint happy.


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_cached_mosaiq_cursor(
    hostname: str, port: int = 1433, database: str = "MOSAIQ", alias=None
):
    return get_uncached_mosaiq_cursor(
        hostname=hostname, port=port, database=database, alias=alias
    )


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_cached_mosaiq_cursor_in_dict(
    hostname: str, port: int = 1433, database: str = "MOSAIQ", alias=None
):
    """This allows the output cursor cache to be mutated by the user code"""
    return {
        "cursor": get_uncached_mosaiq_cursor(
            hostname=hostname, port=port, database=database, alias=alias
        )
    }
