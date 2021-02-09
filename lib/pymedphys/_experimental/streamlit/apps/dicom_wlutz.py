# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

CATEGORY = categories.PLANNING
TITLE = "DICOM WLutz"


def main():
    left_column, right_column = st.beta_columns(2)

    with left_column:
        st.write("## Upload DICOM file")
        dicom_bytes = st.file_uploader("DICOM file")

    if not dicom_bytes:
        raise st.stop()

    with right_column:
        st.write(
            f"""

            ## Details

            * Patient ID: `{datasets[0].PatientID}`
            * Patient Name: `{get_pretty_patient_name_from_dicom_dataset(datasets[0])}`
            """
        )
