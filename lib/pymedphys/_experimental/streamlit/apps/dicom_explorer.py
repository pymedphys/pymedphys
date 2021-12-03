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

import textwrap

from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.streamlit.utilities.dicom import loader as _loader

CATEGORY = categories.PLANNING
TITLE = "DICOM Explorer"


def main():
    dicom_datasets = _loader.dicom_file_loader(
        accept_multiple_files=False, stop_before_pixels=True
    )
    dicom_header = dicom_datasets[0]

    st.markdown(
        textwrap.dedent(
            """\
            ```
            {}
            ```
            """
        ).format(dicom_header.__repr__())
    )
