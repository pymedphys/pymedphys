"""Copyright (C) 2021 Matthew Jennings

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import copy
import pathlib

from pymedphys._imports import streamlit as st

import numpy as np

import pydicom
from pydicom.errors import InvalidDicomError

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._streamlit import categories

STREAMLIT_STATIC_PATH = pathlib.Path(st.__path__[0]) / "static"
DOWNLOADS_PATH = STREAMLIT_STATIC_PATH / "downloads"
if not DOWNLOADS_PATH.is_dir():
    DOWNLOADS_PATH.mkdir()
SUMMED_DOSE_PATH = DOWNLOADS_PATH / "RD.Summed.dcm"

CATEGORY = categories.PRE_ALPHA
TITLE = "Sum Coincident DICOM Doses"

HERE = pathlib.Path(__file__).parent.resolve()


def _axes_in_datasets_match(datasets):

    # Quick shape (sanity) check
    if not all(
        ds.pixel_array.shape == datasets[0].pixel_array.shape for ds in datasets
    ):
        return False

    # Full coord check:
    all_concat_axes = [np.concatenate(xyz_axes_from_dataset(ds)) for ds in datasets]

    return all(np.allclose(a, all_concat_axes[0]) for a in all_concat_axes)


def _check_files_valid(files):
    datasets = []

    for fh in files:
        try:
            ds = pydicom.dcmread(fh)
        except InvalidDicomError:
            st.error(f"{fh.name} is not a valid DICOM file")
            return None

        if not ds.Modality == "RTDOSE":
            st.error(f"File {fh.name} is not a valid DICOM RT Dose file")
            return None

        datasets.append(ds)

    return datasets


def sum_doses_in_datasets(datasets: list[pydicom.dataset.Dataset]):
    """Sum two or more DICOM dose grids and save to new DICOM RT
    Dose dataset"

    Parameters
    ----------
    datasets : list of pydicom.dataset.Dataset
        [description]

    Returns
    -------
    ds_summed : pydicom.dataset.Dataset
        A new DICOM RT Dose dataset whose dose is the sum of all doses
        within `datasets`
    """

    ds_summed = copy.deepcopy(datasets[0])

    ds_summed.DoseSummationType = "MULTI_PLAN"

    doses = np.array([dose_from_dataset(ds) for ds in datasets])
    doses_summed = np.sum(doses, axis=0, dtype=np.float32)

    # ds_summed.DoseGridScaling = np.max(doses_summed) / (2 ^ int(ds_summed.HighBit))

    ds_summed.DoseGridScaling = np.max(doses_summed) / (2 ** 32 - 1)
    pixel_array_summed = (doses_summed / ds_summed.DoseGridScaling).astype(np.uint32)

    ds_summed.PixelData = pixel_array_summed.tobytes()

    st.write(np.max(datasets[0].pixel_array))
    st.write(np.max(ds_summed.pixel_array))

    return ds_summed


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
                ds_summed.save_as(SUMMED_DOSE_PATH)
                st.markdown(
                    "Download the summed DICOM dose file from "
                    "[downloads/RD.summed.dcm](downloads/RD.summed.dcm)"
                )
            else:
                st.write("mismatch")
