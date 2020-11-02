# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._gui.streamlit.mudensity import (
    _config,
    _deliveries,
    _exceptions,
    _utilities,
)
from pymedphys._utilities import patient as utl_patient


@st.cache
def read_trf(trf):
    return pymedphys.read_trf(trf)


def _attempt_patient_name_from_mosaiq(headers):
    st.write(
        """
        #### Corresponding Mosaiq SQL Details
        """
    )

    try:
        mosaiq_details = _config.get_logfile_mosaiq_info(headers)
    except KeyError:
        st.write(
            _exceptions.NoMosaiqAccess(
                "Need Mosaiq access to determine patient name. "
                "Patient name set to 'Unknown'."
            )
        )
        patient_name = "Unknown"

        return patient_name

    mosaiq_details = mosaiq_details.drop("beam_completed", axis=1)
    st.write(mosaiq_details)

    patient_names = set()
    for _, row in mosaiq_details.iterrows():
        st.write(row)
        patient_name = utl_patient.convert_patient_name_from_split(
            row["last_name"], row["first_name"]
        )
        patient_names.add(patient_name)

    patient_name = _utilities.filter_patient_names(patient_names)

    return patient_name


def trf_input_method(patient_id="", key_namespace="", **_):
    """Streamlit GUI method to facilitate TRF data provision.

    Notes
    -----
    TRF files themselves have no innate patient alignment. An option
    for TRF collection is to use the CLI tool
    ``pymedphys trf orchestrate``. This connects to the SAMBA server
    hosted on the Elekta NSS and downloads the diagnostic backup zips.
    It then takes these TRF files and queries the Mosaiq database using
    time of delivery to identify these with a patient id (Ident.Pat_ID1)
    and name.

    As such, all references to patient ID and name within this
    ``trf_input_method`` are actually a reference to their Mosaiq
    database counterparts.
    """
    FILE_UPLOAD = "File upload"
    INDEXED_TRF_SEARCH = "Search indexed TRF directory"

    import_method = st.radio(
        "TRF import method",
        [FILE_UPLOAD, INDEXED_TRF_SEARCH],
        key=f"{key_namespace}_trf_file_import_method",
    )

    if import_method == FILE_UPLOAD:
        selected_files = st.file_uploader(
            "Upload TRF files",
            key=f"{key_namespace}_trf_file_uploader",
            accept_multiple_files=True,
        )

        if not selected_files:
            return {}

        data_paths = []
        individual_identifiers = ["Uploaded TRF file(s)"]

    if import_method == INDEXED_TRF_SEARCH:
        try:
            indexed_trf_directory = _config.get_indexed_trf_directory()
        except KeyError:
            st.write(
                _exceptions.ConfigMissing(
                    "No indexed TRF directory is configured. Please use "
                    f"'{FILE_UPLOAD}' instead."
                )
            )
            return {}

        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        )
        st.write(patient_id)

        filepaths = list(indexed_trf_directory.glob(f"*/{patient_id}_*/*/*/*/*.trf"))

        raw_timestamps = [
            "_".join(path.parent.name.split("_")[0:2]) for path in filepaths
        ]
        timestamps = list(
            pd.to_datetime(raw_timestamps, format="%Y-%m-%d_%H%M%S").astype(str)
        )

        timestamp_filepath_map = dict(zip(timestamps, filepaths))

        timestamps = sorted(timestamps, reverse=True)

        if len(timestamps) == 0:
            if patient_id != "":
                st.write(
                    st_exceptions.NoRecordsFound(
                        f"No TRF log file found for patient ID {patient_id}"
                    )
                )
            return {"patient_id": patient_id}

        if len(timestamps) == 1:
            default_timestamp = timestamps[0]
        else:
            default_timestamp = []

        selected_trf_deliveries = st.multiselect(
            "Select TRF delivery timestamp(s)",
            timestamps,
            default=default_timestamp,
            key=f"{key_namespace}_trf_deliveries",
        )

        if not selected_trf_deliveries:
            return {}

        st.write(
            """
            #### TRF filepath(s)
            """
        )

        selected_files = [
            timestamp_filepath_map[timestamp] for timestamp in selected_trf_deliveries
        ]
        st.write([str(path.resolve()) for path in selected_files])

        individual_identifiers = [
            f"{path.parent.parent.parent.parent.name} {path.parent.name}"
            for path in selected_files
        ]

        data_paths = selected_files

    st.write(
        """
        #### Log file header(s)
        """
    )

    headers = []
    tables = []
    for path_or_binary in selected_files:
        header, table = read_trf(path_or_binary)
        headers.append(header)
        tables.append(table)

    headers = pd.concat(headers)
    headers.reset_index(inplace=True)
    headers.drop("index", axis=1, inplace=True)

    st.write(headers)

    deliveries = _deliveries.cached_deliveries_loading(
        tables, _deliveries.delivery_from_trf
    )

    identifier = f"TRF ({individual_identifiers[0]})"

    patient_name = _attempt_patient_name_from_mosaiq(headers)

    return {
        "site": None,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": data_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }
