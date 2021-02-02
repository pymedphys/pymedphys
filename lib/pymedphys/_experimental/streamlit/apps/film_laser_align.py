# Copyright (C) 2021 Jacob McAloney, Simon Biggs, Cancer Care Associates

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

from pymedphys._streamlit import categories

CATEGORY = categories.PLANNING
TITLE = "Film laser alignment"


def main():
    st.write("Hi Simon!")

    left_column, right_column = st.beta_columns(2)

    with left_column:
        st.write("## Upload DICOM file")
        dicom_bytes = st.file_uploader("DICOM file")

    with right_column:
        st.write("Something else")

    st.write("Below the columns")
