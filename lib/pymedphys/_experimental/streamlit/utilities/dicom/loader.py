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

# TODO: Move this into the "stable" library. Alongside a file
# `pymedphys/_streamlit/utilities/dicom/__init__.py` would be
# appropriate. I'm leaving this detail here in case someone else wants
# to pick up the batton of doing this while I'm gone :).

import collections
from typing import BinaryIO, Sequence, Union, cast

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._dicom import utilities as _dcm_utilities

File = BinaryIO
Files = Sequence[File]
UploadedFiles = Union[Files, File]


def dicom_file_loader(
    accept_multiple_files: bool, stop_before_pixels: bool
) -> Sequence["pydicom.Dataset"]:
    """A Streamlit component that provides DICOM upload functionality.

    Parameters
    ----------
    accept_multiple_files : ``bool``
        Whether or not the wrapped
        `st.file_uploader <https://docs.streamlit.io/en/stable/api.html#streamlit.file_uploader>`_
        utility will accept multiple uploads. This argument is directly
        passed through as a keyword parameter to ``st.file_uploader``.
    stop_before_pixels : ``bool``
        Whether or not the wrapped
        `pydicom.dcmread <https://pydicom.github.io/pydicom/dev/reference/generated/pydicom.filereader.dcmread.html#pydicom.filereader.dcmread>`_
        will read the pixel values of the DICOM file or stop reading the
        header before loading the pixel values. This argument is
        directly passed through as a keyword parameter to
        ``pydicom.dcmread``

    Returns
    -------
    datasets : a list of ``pydicom.Dataset``
        The PyDICOM datasets corresponding to the files uploaded by the
        user.
    """
    left_column, right_column = st.beta_columns(2)

    if accept_multiple_files:
        file_string = "files"
    else:
        file_string = "file"

    with left_column:
        st.write(f"## Upload DICOM {file_string}")

        # This is specifically not limited to .dcm extensions as
        # sometimes DICOM exports to file don't have any file extension.
        files: UploadedFiles = st.file_uploader(
            f"DICOM {file_string}", accept_multiple_files=accept_multiple_files
        )

    if not files:
        raise st.stop()

    assumed_sequence = cast(Files, files)

    try:
        assumed_sequence[0]
    except TypeError:
        # If the return from file uploader is not indexable
        a_single_file = cast(File, files)
        files = [a_single_file]

    files = cast(Files, files)

    datasets = []
    for a_file in files:
        try:
            a_file.seek(0)
            dataset = pydicom.dcmread(
                a_file, force=True, stop_before_pixels=stop_before_pixels
            )
        except Exception as e:
            st.warning(
                f'Failed reading the file "`{a_file.name}`". The error was the following:'
            )
            st.error(e)
            st.stop()
            raise

        datasets.append(dataset)

    patient_id_filenames_map = collections.defaultdict(set)
    patient_id_names_map = collections.defaultdict(set)
    for dataset, a_file in zip(datasets, files):
        patient_id = dataset.PatientID
        patient_name = _dcm_utilities.pretty_patient_name(dataset)
        patient_id_filenames_map[patient_id].add(a_file.name)
        patient_id_names_map[patient_id].add(patient_name)

    with right_column:
        st.write("## Details")

        for patient_id, filenames in patient_id_filenames_map.items():
            patient_names = patient_id_names_map[patient_id]

            st.write(
                f"""
                * {_optionally_write_with_plural("Filename", filenames)}
                * Patient ID: `{patient_id}`
                * {_optionally_write_with_plural("Patient Name", patient_names)}
                """
            )

    return datasets


def _optionally_write_with_plural(label, items):
    if len(items) > 1:
        label += "s"

    items_as_markdown = "`, `".join(items)
    markdown_to_display = f"{label}: `{items_as_markdown}`"

    return markdown_to_display
