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

from pymedphys._imports import dbfread
from pymedphys._imports import streamlit as st

SITE_DATABASE_DIRECTORIES = {
    "rccc": pathlib.Path(r"\\pdc\PExIT\DataExchange\iViewDB"),
    "nbcc": pathlib.Path(r"\\tunnel-nbcc-pdc\Physics\NBCC-DataExchange\iViewDB"),
    "sash": pathlib.Path(r"\\tunnel-sash-physics-server\iViewDB"),
}


@st.cache()
def get_dbf_table(path):
    return dbfread.DBF(path)


def main():
    st.title("iView Database Explorer")

    site = st.radio("Site", list(SITE_DATABASE_DIRECTORIES.keys()))

    database_directory = SITE_DATABASE_DIRECTORIES[site]

    database_paths = {
        path.stem.lower(): path for path in database_directory.glob("*.dbf")
    }

    table_records = {key: get_dbf_table(path) for key, path in database_paths.items()}

    table_to_view = st.selectbox("Table to view", list(table_records.keys()))

    st.write(list(table_records[table_to_view]))
