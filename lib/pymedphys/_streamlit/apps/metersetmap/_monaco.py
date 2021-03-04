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

from pymedphys._imports import streamlit as st

from pymedphys._streamlit.apps.metersetmap import _deliveries
from pymedphys._streamlit.utilities import exceptions as _exceptions
from pymedphys._streamlit.utilities import monaco as st_monaco


def monaco_input_method(
    config, patient_id="", key_namespace="", advanced_mode=False, site=None, **_
):
    telfile_picker_results = st_monaco.monaco_tel_files_picker(
        config,
        patient_id,
        key_namespace,
        advanced_mode,
        site,
        plan_selection_text=(
            """
            Select the Monaco plan that correspond to a patient's single fraction.
            If a patient has multiple fraction types (such as a plan with a boost)
            then these fraction types need to be analysed separately.
            """
        ),
    )

    monaco_site, patient_id, patient_name, selected_monaco_plan, tel_paths = [
        telfile_picker_results[key]
        for key in (
            "monaco_site",
            "patient_id",
            "patient_name",
            "selected_monaco_plan",
            "tel_paths",
        )
    ]

    if advanced_mode:
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
