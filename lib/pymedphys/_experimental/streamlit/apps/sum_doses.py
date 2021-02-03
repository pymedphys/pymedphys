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
import os
import pathlib
from typing import List, Sequence, Union

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


def _check_files_valid(
    files: Sequence[Union[str, bytes, os.PathLike]]
) -> List[pydicom.dataset.Dataset]:

    if not len(files) >= 2:
        raise ValueError("`files` must contain at least 2 elements")

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

        if not ds.DoseSummationTypes == "PLAN":
            st.error(f"File {fh.name} is not a 'plan' dose")
            return None

        datasets.append(ds)

    return datasets


def coords_in_datasets_are_equal(datasets: Sequence[pydicom.dataset.Dataset]) -> bool:
    """True if all DICOM datasets have perfectly matching coordinates

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM datasets whose coordinates are to be
        compared.

    Returns
    -------
    bool
        True if coordinates match for all datasets, False otherwise.
    """

    if not len(datasets) >= 2:
        raise ValueError("At least two datasets must be provided for comparison")

    # Quick shape (sanity) check
    if not all(
        ds.pixel_array.shape == datasets[0].pixel_array.shape for ds in datasets
    ):
        return False

    # Full coord check:
    all_concat_axes = [np.concatenate(xyz_axes_from_dataset(ds)) for ds in datasets]

    return all(np.allclose(a, all_concat_axes[0]) for a in all_concat_axes)


def patient_ids_in_datasets_are_equal(datasets: list[pydicom.dataset.Dataset]) -> bool:
    """True if all DICOM datasets have the same Patient ID

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM datasets whose Patient IDs are to be
        compared.

    Returns
    -------
    bool
        True if Patient IDs match for all datasets, False otherwise.
    """

    if not len(datasets) >= 2:
        raise ValueError("At least two datasets must be provided for comparison")

    return all(ds.PatientId == datasets[0].PatientId for ds in datasets)


def sum_doses_in_datasets(datasets: list[pydicom.dataset.Dataset]):
    """Sum two or more DICOM dose grids and save to new DICOM RT
    Dose dataset"

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM RT Dose datasets whose doses are to be
        summed.

    Returns
    -------
    pydicom.dataset.Dataset
        A new DICOM RT Dose dataset whose dose is the sum of all doses
        within `datasets`
    """

    if not len(datasets) >= 2:
        raise ValueError("At least two datasets must be provided for comparison")

    if not all(ds.Modality == "RTDOSE" for ds in datasets):
        raise ValueError("`datasets` must only contain DICOM RT Dose datasets.")

    if not patient_ids_in_datasets_are_equal(datasets):
        raise ValueError("Patient ID must match for all datasets")

    if not all(ds.DoseSummationType == "PLAN" for ds in datasets):
        raise ValueError(
            "Only DICOM RT Doses whose DoseSummationTypes are 'PLAN' are supported"
        )
    if not coords_in_datasets_are_equal(datasets):
        raise ValueError("All dose grids must have perfectly coincident coordinates")

    ds_summed = copy.deepcopy(datasets[0])

    ds_summed.DoseSummationType = "MULTI_PLAN"

    if not all(ds.DoseType in ("PHYSICAL", "EFFECTIVE") for ds in datasets):
        raise ValueError(
            "Only DICOM RT Doses whose DoseTypes are 'PHYSICAL' or "
            "'EFFECTIVE' are supported"
        )
    elif any(ds.DoseType == "EFFECTIVE" for ds in datasets):
        ds_summed.DoseType = "EFFECTIVE"
    else:
        ds_summed.DoseType = "PHYSICAL"
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
            ds_summed = sum_doses_in_datasets(datasets)
            ds_summed.save_as(SUMMED_DOSE_PATH)
            st.markdown(
                "Download the summed DICOM dose file from "
                "[downloads/RD.summed.dcm](downloads/RD.summed.dcm)"
            )
