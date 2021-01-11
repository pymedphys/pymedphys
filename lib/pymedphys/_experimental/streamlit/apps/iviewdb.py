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

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import xmltodict

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc

from pymedphys._experimental.streamlit.utilities import dbf

CATEGORY = categories.PLANNING
TITLE = "iView Database Explorer"


@st.cache()
def get_files_for_extension(directory: pathlib.Path, extension: str):
    """Cached file list.

    Parameters
    ----------
    directory
        The directory within which to search
    extension
        The extension to recursively search for

    """
    return [
        str(item.relative_to(directory)) for item in directory.glob(f"**/*{extension}")
    ]


def main():
    config = _config.get_config()

    st.write(
        """
            This tool was created to for my (Simon) own exploration
            while building the Winston Lutz GUI. It is not intended to
            ever come out of an experimental state (unless some amazing
            use case is found).

            For now, it is simply an exploratory tool, shared in the
            small chance that someone might find it helpful.
        """
    )

    _, database_directory = misc.get_site_and_directory(
        config, "Database Site", "iviewdb"
    )

    database_paths = {
        path.stem.lower(): path
        for path in database_directory.glob("*.DBF")
        if not path.stem.endswith("_N")
    }

    table_records = {
        key: dbf.get_dbf_table(path) for key, path in database_paths.items()
    }

    table_to_view = st.radio("Table to view", list(table_records.keys()))

    dbf_record = table_records[table_to_view]

    st.write("## Field Names")

    field_names = dbf_record.field_names

    selected_fields = st.multiselect(
        "Field names to view", field_names, default=field_names
    )

    if selected_fields:
        full_pandas_table = pd.DataFrame(iter(dbf_record))
        st.write(full_pandas_table[selected_fields])

    st.write("## File lists")

    if st.button("Show *.jpg files"):
        st.write(get_files_for_extension(database_directory, ".jpg"))

    xml_files = get_files_for_extension(database_directory, ".xml")

    if st.button("Show *.xml files"):
        st.write(xml_files)

    st.write("## Display XML")

    chosen_file = st.selectbox("Select XML file", options=xml_files)

    try:
        xml_path = database_directory.joinpath(chosen_file)
    except TypeError:
        st.stop()

    with open(xml_path) as fd:
        doc = xmltodict.parse(fd.read())

    st.write(doc)
