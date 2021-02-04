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
from typing import BinaryIO, List, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._dicom.header import pretty_patient_name
from pymedphys._streamlit import categories

CATEGORY = categories.PRE_ALPHA
TITLE = "Sum Coincident DICOM Doses"


def main():
    left_column, right_column = st.beta_columns(2)

    with left_column:
        st.write("## Upload DICOM RT Dose files")
        files: Sequence[BinaryIO] = st.file_uploader(
            "Upload at least two DICOM RT Dose files whose doses you'd "
            "like to add together. The first file uploaded will be "
            "used as a template for the summed DICOM RT Dose file.",
            ["dcm"],
            accept_multiple_files=True,
        )

    if not files:
        st.stop()

    try:
        datasets = _load_and_check_files_valid(files)
    except ValueError as e:
        st.write(e)
        st.stop()

    if st.button("Click to Sum Doses"):

        with right_column:
            st.write(
                f"""

                ## Details

                * Patient ID: `{datasets[0].PatientID}`
                * Patient Name: `{pretty_patient_name(datasets[0])}`
                """
            )

        if len(datasets) < 2:
            # Note that if the user tries to remove a file that has
            # already been uploaded, the filename disappears from view
            # BUT st.file_uploader doesn't delete this file.
            raise ValueError("Please upload at least two DICOM RT Dose files.")

        st.write("---")
        st.write("Summing doses...")

        ds_summed = sum_doses_in_datasets(datasets)
        _save_dataset_to_downloads_dir(ds_summed)

        st.write("Done!")
        st.markdown(
            "*Download the summed DICOM dose file from "
            "[downloads/RD.summed.dcm](downloads/RD.summed.dcm)*"
        )


def _load_and_check_files_valid(
    files: Sequence[BinaryIO],
) -> List["pydicom.dataset.Dataset"]:

    ds0 = _load_dicom_file(files[0])
    datasets = [ds0]

    for fh in files[1:]:
        ds = _load_dicom_file(fh)

        if ds.PatientID != ds0.PatientID:
            st.error(
                f"'{fh.name}' has a different PatientID ({ds.PatientID}) "
                f"from '{files[0].name}' ({ds0.PatientID})."
            )

        datasets.append(ds)

    return datasets


def _load_dicom_file(fh: BinaryIO):
    try:
        ds = pydicom.dcmread(fh)
    except pydicom.errors.InvalidDicomError as e:
        raise ValueError(f"'{fh.name}' is not a valid DICOM file") from e

    try:
        _validate_dicom_dataset(ds)
    except ValueError:
        st.error(f"When trying to load {fh.name}, the following error occurred:")

        raise

    return ds


def _validate_dicom_dataset(ds):
    if ds.Modality != "RTDOSE":
        raise ValueError("DICOM dataset is not RT Dose")

    if ds.DoseSummationType != "PLAN":
        raise ValueError("DICOM dataset is not a 'plan' dose")

    if ds.DoseUnits != "GY":
        raise ValueError("DICOM dataset must contain absolute dose")


def _save_dataset_to_downloads_dir(ds: "pydicom.dataset.Dataset"):
    STREAMLIT_STATIC_PATH = pathlib.Path(st.__path__[0]) / "static"

    DOWNLOADS_PATH = STREAMLIT_STATIC_PATH / "downloads"
    DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)

    ds.save_as(DOWNLOADS_PATH / "RD.Summed.dcm")


def coords_in_datasets_are_equal(datasets: Sequence["pydicom.dataset.Dataset"]) -> bool:
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


def patient_ids_in_datasets_are_equal(
    datasets: Sequence["pydicom.dataset.Dataset"],
) -> bool:
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

    return all(ds.PatientID == datasets[0].PatientID for ds in datasets)


def sum_doses_in_datasets(
    datasets: Sequence["pydicom.dataset.Dataset"],
) -> "pydicom.dataset.Dataset":
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

    if not all(ds.DoseUnits == datasets[0].DoseUnits for ds in datasets):
        raise ValueError(
            "All DICOM RT Doses must have the same units ('GY or 'RELATIVE')"
        )

    if not coords_in_datasets_are_equal(datasets):
        raise ValueError("All dose grids must have perfectly coincident coordinates")

    ds_summed = copy.deepcopy(datasets[0])

    ds_summed.BitsAllocated = 32
    ds_summed.BitsStored = 32
    ds_summed.DoseSummationType = "MULTI_PLAN"
    ds_summed.DoseComment = "Summed Dose"

    if not all(ds.DoseType in ("PHYSICAL", "EFFECTIVE") for ds in datasets):
        raise ValueError(
            "Only DICOM RT Doses whose DoseTypes are 'PHYSICAL' or "
            "'EFFECTIVE' are supported"
        )
    if any(ds.DoseType == "EFFECTIVE" for ds in datasets):
        ds_summed.DoseType = "EFFECTIVE"
    else:
        ds_summed.DoseType = "PHYSICAL"
    doses = np.array([dose_from_dataset(ds) for ds in datasets])
    doses_summed = np.sum(doses, axis=0, dtype=np.float32)

    # ds_summed.DoseGridScaling = np.max(doses_summed) / (2 ^ int(ds_summed.HighBit))

    ds_summed.DoseGridScaling = np.max(doses_summed) / (2 ** 32 - 1)
    pixel_array_summed = (doses_summed / ds_summed.DoseGridScaling).astype(np.uint32)

    ds_summed.PixelData = pixel_array_summed.tobytes()

    return ds_summed
