"""Streamlit Gui for Pseudonymise
"""
# Copyright (C) 2020 Stuart Swerdloff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import base64
import datetime
import io
import pathlib
from zipfile import ZIP_DEFLATED, ZipFile

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._dicom.anonymise import anonymise_dataset
from pymedphys._dicom.constants.core import DICOM_SOP_CLASS_NAMES_MODE_PREFIXES
from pymedphys._dicom.utilities import remove_file
from pymedphys._streamlit import categories
from pymedphys.experimental import pseudonymisation as pseudonymisation_api

CATEGORY = categories.BETA
TITLE = "DICOM Pseudonymisation"


def link_to_zipbuffer_download(filename: str, zip_bytes: bytes):
    """Generates a link allowing the bytes to be downloaded using the specified filename
    Assumes that the data is in zip format

    Parameters
    ----------
    filename : str
        default filename to use
    zip_bytes : bytes
        the bytes from an IOBytes in which a ZipFile wrote its contents, or the bytes
        read directly from a zip file on disk
    """
    b64 = base64.b64encode(zip_bytes).decode()
    href = f"<a href=\"data:file/zip;base64,{b64}\" download='{filename}'>\
        Click to download {filename}\
    </a>"
    st.sidebar.markdown(href, unsafe_allow_html=True)


def build_pseudonymised_file_name(ds_input: pydicom.dataset.Dataset):
    """Create the base filename for the pseudonymised file

    Parameters
    ----------
    ds_input : pydicom.dataset.Dataset
        The non-pseudonymised DICOM data

    Returns
    -------
    anon_filename : str
        name for the pseudonymised file, which can be used
        for addition to a zip
    """
    pseudo_sop_instance_uid = pseudonymisation_api.pseudonymisation_dispatch[  # type: ignore
        "UI"
    ](
        ds_input.SOPInstanceUID
    )

    sop_class_uid: pydicom.dataelem.DataElement = ds_input.SOPClassUID

    mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[sop_class_uid.name]
    anon_filename = f"{mode_prefix}.{pseudo_sop_instance_uid}_Anonymised.dcm"

    return anon_filename


def _zip_pseudo_fifty_mbytes(file_buffer_list: list, zip_bytes_io: io.BytesIO):
    """Pseudonymises the contents of the file_buffer_list (list of DICOM files)
    and places the pseudonymised files in to a zip.

    Parameters
    ----------
    file_buffer_list : list
        List of DICOM file buffers from streamlit file_uploader to pseudonymise
    zip_bytes_io : io.BytesIO
        An in memory file like object to be used for storing the Zip

    """

    bad_data = False
    file_count = 0
    keywords = pseudonymisation_api.get_default_pseudonymisation_keywords()
    keywords.remove("PatientSex")
    strategy = pseudonymisation_api.pseudonymisation_dispatch
    zip_stream = zip_bytes_io

    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as myzip:
        for uploaded_file_buffer in file_buffer_list:
            file_count += 1

            # don't close the buffers.  Streamlit provides the user with control over that.
            # might be appropriate to close the buffers in some circumstances,
            # but then when the user goes to close the buffer (click x on screen)
            # there will be an error.

            try:
                original_file_name = uploaded_file_buffer.name
                ds_input: pydicom.FileDataset = pydicom.dcmread(
                    uploaded_file_buffer, force=True
                )

                anonymise_dataset(
                    ds_input,
                    delete_private_tags=True,
                    delete_unknown_tags=True,
                    copy_dataset=False,  # do the work in place.  less memory used and we're disposing shortly anyway
                    identifying_keywords=keywords,
                    replacement_strategy=strategy,
                )
                temp_anon_filepath = build_pseudonymised_file_name(ds_input)
                in_memory_temp_file = io.BytesIO()
                anon_filename = pathlib.Path(temp_anon_filepath).name
                pydicom.dcmwrite(in_memory_temp_file, ds_input)
            except (KeyError, IOError, ValueError) as e_info:
                print(e_info)
                print(f"While processing {original_file_name}")
                bad_data = True
                break
            myzip.writestr(
                anon_filename,
                in_memory_temp_file.getvalue(),
                compress_type=ZIP_DEFLATED,
            )
            in_memory_temp_file.close()
    return bad_data


def pseudonymise_buffer_list(file_buffer_list: list):
    """Pseudonymises the contents of the file_buffer_list (list of DICOM files)
    and places the pseudonymised files in to a set of zips, each less than 50 MBytes.
    Those zips are then made available for download through a set of links in the
    streamlit.sidebar

    The 50MByte limit is imposed by the href download link limit.

    The compression used is DEFLATE, but the uncompressed contents are kept at just under 50 MBytes
    If a single original uncompressed file is > 50MByte, and does not compress to under 50 MByte
    that file will fail to be made available for download, and may cause the entire pseudonymisation
    attempt to fail.

    Parameters
    ----------
    file_buffer_list : list
        DICOM files that were uploaded using streamlit.file_uploader
    """

    if file_buffer_list is not None and len(file_buffer_list) > 0:
        my_date_time = datetime.datetime.now()
        str_now_datetime = my_date_time.strftime("%Y%m%d_%H%M%S")
        zipfile_basename = f"Pseudonymised_{str_now_datetime}"

        bad_data = False
        index_to_fifty_mbyte_increment = _gen_index_list_to_fifty_mbyte_increment(
            file_buffer_list
        )

        st.write(index_to_fifty_mbyte_increment)

        zip_count = 0
        start_index = 0
        for end_index in index_to_fifty_mbyte_increment:
            if start_index == end_index:
                break
            zip_count += 1
            zipfile_name = f"{zipfile_basename}.{zip_count}.zip"
            zip_bytes_io = io.BytesIO()
            bad_data = _zip_pseudo_fifty_mbytes(
                file_buffer_list[start_index:end_index], zip_bytes_io
            )
            start_index = end_index
            if bad_data:
                if zip_bytes_io is not None:
                    zip_bytes_io.close()
                    del zip_bytes_io
                else:
                    remove_file(zipfile_name)
                st.text("Problem processing DICOM data")
            else:
                if zip_bytes_io is not None:
                    link_to_zipbuffer_download(zipfile_name, zip_bytes_io.getvalue())
                    zip_bytes_io.close()
                    del zip_bytes_io


def _gen_index_list_to_fifty_mbyte_increment(file_buffer_list):
    """Create a list of indexes marking the ~50 MByte increments of cumulative size
    of the file_buffers provided by the streamlit.file_uploader

    Parameters
    ----------
    file_buffer_list : ``list``
        list of file_buffers (derived from io.BytesIO) obtained from streamlit.file_uploader

    Returns
    -------
    ``list``
        list of indexes marking the ~50 MByte increments, including the last index
    """

    file_count = 0
    index_to_fifty_mbyte_increment = list()
    size = 0
    for uploaded_file_buffer in file_buffer_list:
        file_count += 1
        size += uploaded_file_buffer.size
        if size > 50000000:
            index_to_fifty_mbyte_increment.append(file_count)
            size = 0

    if size != 0:
        index_to_fifty_mbyte_increment.append(file_count)

    return index_to_fifty_mbyte_increment


def main():
    uploaded_file_buffer_list = st.file_uploader(
        "Files to pseudonymise, refresh page after downloading zip(s)",
        ["dcm"],
        accept_multiple_files=True,
    )

    if st.button("Pseudonymise", key="PseudonymiseButton"):
        pseudonymise_buffer_list(uploaded_file_buffer_list)
        uploaded_file_buffer_list.clear()

    # this deletion never worked.  which motivated switch to using IOBytes for ZipFile
    # if st.button(f"Delete Zip(s)", key="DeleteZip"):
    #     for zip_path_str in zip_path_list:
    #         remove_file(zip_path_str)


if __name__ == "__main__":
    main()
