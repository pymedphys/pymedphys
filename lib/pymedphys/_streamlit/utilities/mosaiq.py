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

from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import connect as msq_connect


def uncached_get_mosaiq_cursor(server):
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
    username, password = msq_connect.get_username_and_password_without_prompt(server)

    if password:
        try:
            conn = msq_connect.connect_with_credential(server, username, password)
            cursor = conn.cursor()
            return cursor
        except msq_connect.WrongUsernameOrPassword as e:
            st.write(e)

    st.write("## Login to Mosaiq SQL Database")

    if not username:
        username = ""

    username = st.text_input(
        label=f"Username for the SQL server on {server}",
        value=username,
        key=f"MosaiqSQLUsername_{server}",
    )

    if username:
        msq_connect.save_username(server, username)

    if not password:
        password = ""

    password = st.text_input(
        label="Password",
        value=password,
        type="password",
        key=f"MosaiqSQLPassword_{server}",
    )

    if password:
        msq_connect.save_password(server, password)

    if st.button("Connect"):
        st.experimental_rerun()

    st.stop()

    return None


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_mosaiq_cursor(server):
    return uncached_get_mosaiq_cursor(server)


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def get_mosaiq_cursor_in_bucket(server):
    """This allows the output cursor cache to be mutated by the user code
    """
    return {"cursor": uncached_get_mosaiq_cursor(server)}
