# Copyright (C) 2021 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""

import pathlib
import shutil
import tempfile

from pymedphys._imports import streamlit as st

import pydicom
from pydicom.errors import InvalidDicomError

from pymedphys._streamlit import categories

# from pymedphys._streamlit.utilities import config as _config

CATEGORY = categories.PRE_ALPHA
TITLE = "Sum Two DICOM Doses"

HERE = pathlib.Path(__file__).parent.resolve()


def _check_files_valid(files):
    datasets = []

    for i, fh in enumerate(files):
        n = i + 1
        try:
            datasets.append(pydicom.dcmread(fh))
        except TypeError:
            st.error(f"Please select file {n}!")
            return None
        except InvalidDicomError:
            st.error(f"File {n} is not a valid DICOM file")
            return None

        if not ds.Modality == "RTDOSE":
            st.error(f"File {n} is not a valid DICOM RT Dose file")
            return None

    return datasets


def main():

    fh1 = st.file_uploader(
        "Upload the first DICOM Dose file. This is used as a template"
        "for the summed dose",
        ["dcm"],
        accept_multiple_files=False,
    )

    fh2 = st.file_uploader(
        "Upload the second DICOM Dose file.",
        ["dcm"],
        accept_multiple_files=False,
    )

    if st.button("Sum Doses"):

        datasets = _check_files_valid([fh1, fh2])

        # if datasets:
        #     doses =
