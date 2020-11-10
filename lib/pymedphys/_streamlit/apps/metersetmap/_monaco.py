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

import os

from pymedphys._imports import streamlit as st

from pymedphys._monaco import patient as mnc_patient
from pymedphys._streamlit.apps.metersetmap import _deliveries
from pymedphys._streamlit.utilities import exceptions as _exceptions
from pymedphys._streamlit.utilities import monaco as st_monaco


@st.cache
def read_monaco_patient_name(monaco_patient_directory):
    return mnc_patient.read_patient_name(monaco_patient_directory)


def monaco_input_method(
    patient_id="", key_namespace="", advanced_mode_local=False, site=None, **_
):
    (
        monaco_site,
        monaco_directory,
        patient_id,
        plan_directory,
        patient_directory,
    ) = st_monaco.monaco_patient_directory_picker(
        patient_id, key_namespace, advanced_mode_local, site
    )

    patient_name = read_monaco_patient_name(str(patient_directory))

    st.write(f"Patient Name: `{patient_name}`")

    all_tel_paths = list(plan_directory.glob("**/*tel.1"))
    all_tel_paths = sorted(all_tel_paths, key=os.path.getmtime)

    plan_names_to_choose_from = [
        str(path.relative_to(plan_directory)) for path in all_tel_paths
    ]

    if len(plan_names_to_choose_from) == 0:
        if patient_id != "":
            st.write(
                _exceptions.NoRecordsFound(
                    f"No Monaco plans found for patient ID {patient_id}"
                )
            )
        return {"patient_id": patient_id}

    st.write(
        """
        Select the Monaco plan that correspond to a patient's single fraction.
        If a patient has multiple fraction types (such as a plan with a boost)
        then these fraction types need to be analysed separately.
        """
    )

    selected_monaco_plan = st.radio(
        "Select a Monaco plan",
        plan_names_to_choose_from,
        key=f"{key_namespace}_monaco_plans",
    )

    tel_paths = []

    if selected_monaco_plan is not None:
        current_plans = list(
            monaco_directory.glob(f"*~{patient_id}/plan/{selected_monaco_plan}")
        )
        current_plans = [path.resolve() for path in current_plans]
        if len(current_plans) != 1:
            st.write("Plans found:", current_plans)
            raise ValueError("Exactly one plan should have been found")
        tel_paths += current_plans

    if advanced_mode_local:
        st.write([str(path.resolve()) for path in tel_paths])

    deliveries = _deliveries.cached_deliveries_loading(
        tel_paths, _deliveries.delivery_from_tel
    )

    if tel_paths:
        plan_names = ", ".join([path.parent.name for path in tel_paths])
        identifier = f"Monaco ({plan_names})"
    else:
        identifier = None

    if len(deliveries) == 1 and len(deliveries[0].mu) == 0:
        st.write(
            _exceptions.NoControlPointsFound(
                "This is likely due to an as of yet unsupported "
                "Monaco file format. At this point in time 3DCRT "
                "is not yet supported for reading directly from "
                "Monaco. DICOM is though, please export the plan "
                "to RT DICOM and import the data that way."
            )
        )

    results = {
        "site": monaco_site,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "selected_monaco_plan": selected_monaco_plan,
        "data_paths": tel_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results
