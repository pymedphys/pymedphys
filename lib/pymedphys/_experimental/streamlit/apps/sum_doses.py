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

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._streamlit import categories

# from pymedphys._streamlit.utilities import config as _config

CATEGORY = categories.PRE_ALPHA
TITLE = "Sum Two DICOM Doses"

HERE = pathlib.Path(__file__).parent.resolve()


def _axes_in_datasets_match(datasets):

    all_axes = [xyz_axes_from_dataset(ds) for ds in datasets]

    return all(a == all_axes[0] for a in all_axes)


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


def sum_doses_in_datasets(datasets):

    ds_summed = copy.copy(datasets[0])

    ds_summed.DoseSummationType = "MULTI_PLAN"
    ds_summed.DoseGridScaling = sum([ds.DoseGridScaling for ds in datasets])

    pixel_arrays_rescaled = [
        ds.DoseGridScaling / ds_summed.DoseGridScaling * ds.pixel_array
        for ds in datasets
    ]
    pixel_array_summed = sum(pixel_arrays_rescaled)

    ds_summed.PixelData = pixel_array_summed.tobytes()


def main():

    files = st.file_uploader(
        "Upload DICOM RT Dose files for which to add dose. You must "
        "add two or more. The first file uploaded will be used as a "
        "template for the summed DICOM RT Dose file.",
        ["dcm"],
        accept_multiple_files=True,
    )

    if st.button("Sum Doses"):

        datasets = _check_files_valid(files)

        if datasets:
            if _axes_in_datasets_match(datasets):
                ds_summed = sum_doses_in_datasets(datasets)
