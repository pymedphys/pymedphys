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


import pathlib

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._gui.streamlit.mudensity import _config


def icom_input_method(patient_id="", key_namespace="", advanced_mode_local=False, **_):
    icom_directories = _config.get_default_icom_directories()

    if advanced_mode_local:
        st.write("iCOM patient directories", icom_directories)

    icom_directories = [pathlib.Path(path) for path in icom_directories]

    if advanced_mode_local:
        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        )
        st.write(patient_id)

    icom_deliveries = []
    for path in icom_directories:
        icom_deliveries += list(path.glob(f"{patient_id}_*/*.xz"))

    icom_deliveries = sorted(icom_deliveries)

    icom_files_to_choose_from = [path.stem for path in icom_deliveries]

    timestamps = list(
        pd.to_datetime(icom_files_to_choose_from, format="%Y%m%d_%H%M%S").astype(str)
    )

    choice_path_map = dict(zip(timestamps, icom_deliveries))

    st.write(
        """
        Here you need to select the timestamps that correspond to a single
        fraction of the plan selected above. Most of the time
        you will only need to select one timestamp here, however in some
        cases you may need to select multiple timestamps.

        This can occur if for example a single fraction was delivered in separate
        beams due to either a beam interrupt, or the fraction being spread
        over multiple energies
        """
    )

    if len(timestamps) == 0:
        if patient_id != "":
            st.write(
                _exceptions.NoRecordsFound(
                    f"No iCOM delivery record found for patient ID {patient_id}"
                )
            )
        return {"patient_id": patient_id}

    if len(timestamps) == 1:
        default_timestamp = [timestamps[0]]
    else:
        default_timestamp = []

    timestamps = sorted(timestamps, reverse=True)

    try:
        selected_icom_deliveries = st.multiselect(
            "Select iCOM delivery timestamp(s)",
            timestamps,
            default=default_timestamp,
            key=f"{key_namespace}_icom_deliveries",
        )
    except st.errors.StreamlitAPIException:
        st.write(f"Default timestamp = `{default_timestamp}`")
        st.write(f"All timestamps = `{timestamps}`")
        raise

    icom_filenames = [
        path.replace(" ", "_").replace("-", "").replace(":", "")
        for path in selected_icom_deliveries
    ]

    icom_paths = []
    for selected in selected_icom_deliveries:
        icom_paths.append(choice_path_map[selected])

    if advanced_mode_local:
        st.write([str(path.resolve()) for path in icom_paths])

    patient_names = set()
    for icom_path in icom_paths:
        patient_name = str(icom_path.parent.name).split("_")[-1]
        try:
            patient_name = utl_patient.convert_patient_name_from_split(
                *patient_name.split(", ")
            )
        except:  # pylint: disable = bare-except
            pass

        patient_names.add(patient_name)

    patient_name = _utilities.filter_patient_names(patient_names)

    icom_streams = load_icom_streams(icom_paths)
    deliveries = _deliveries.cached_deliveries_loading(
        icom_streams, _deliveries.delivery_from_icom
    )

    if selected_icom_deliveries:
        identifier = f"iCOM ({icom_filenames[0]})"
    else:
        identifier = None

    if len(deliveries) == 0:
        st.write(_exceptions.InputRequired("Please select at least one iCOM delivery"))
        st.stop()

    results = {
        "site": None,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "selected_icom_deliveries": selected_icom_deliveries,
        "data_paths": icom_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results
