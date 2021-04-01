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

from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._dicom.uid import DICOM_PLAN_UID
from pymedphys._streamlit.apps.metersetmap import _config
from pymedphys._streamlit.utilities import exceptions as _exceptions
from pymedphys._streamlit.utilities import misc as st_misc
from pymedphys._utilities import patient as utl_patient


def pydicom_hash_function(dicom):
    return hash(dicom.SOPInstanceUID)


@st.cache(hash_funcs={pydicom.dataset.FileDataset: pydicom_hash_function})
def load_dicom_file_if_plan(filepath):
    dcm = pydicom.read_file(str(filepath), force=True, stop_before_pixels=True)
    if dcm.SOPClassUID == DICOM_PLAN_UID:
        return dcm

    return None


def dicom_input_method(  # pylint: disable = too-many-return-statements
    config, key_namespace="", patient_id="", site=None, **_
):
    monaco_site = site

    FILE_UPLOAD = "File upload"
    MONACO_SEARCH = "Search Monaco file export location"

    import_method = st.radio(
        "DICOM import method",
        [FILE_UPLOAD, MONACO_SEARCH],
        key=f"{key_namespace}_dicom_file_import_method",
    )

    if import_method == FILE_UPLOAD:
        dicom_plan_bytes = st.file_uploader(
            "Upload DICOM RT Plan File", key=f"{key_namespace}_dicom_plan_uploader"
        )

        if dicom_plan_bytes is None:
            return {}

        try:
            dicom_plan_bytes.seek(0)
            dicom_plan = pydicom.read_file(dicom_plan_bytes, force=True)
        except:  # pylint: disable = bare-except
            st.write(_exceptions.WrongFileType("Does not appear to be a DICOM file"))
            return {}

        if dicom_plan.SOPClassUID != DICOM_PLAN_UID:
            st.write(
                _exceptions.WrongFileType(
                    "The DICOM type needs to be an RT DICOM Plan file"
                )
            )
            return {}

        data_paths = []

    if import_method == MONACO_SEARCH:
        try:
            dicom_export_locations = _config.get_dicom_export_locations(config)
        except KeyError:
            st.write(
                _exceptions.ConfigMissing(
                    "No Monaco directory is configured. Please use "
                    f"'{FILE_UPLOAD}' instead."
                )
            )
            return {}

        monaco_site = st_misc.site_picker(
            config,
            "Monaco Export Location",
            default=monaco_site,
            key=f"{key_namespace}_monaco_site",
        )

        monaco_export_directory = dicom_export_locations[monaco_site]
        st.write(monaco_export_directory.resolve())

        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        )

        found_dicom_files = list(monaco_export_directory.glob(f"{patient_id}_*.dcm"))

        dicom_plans = {}

        for path in found_dicom_files:
            dcm = load_dicom_file_if_plan(path)
            if dcm is not None:
                dicom_plans[path.name] = dcm

        dicom_plan_options = list(dicom_plans.keys())

        if len(dicom_plan_options) == 0 and patient_id != "":
            st.write(
                _exceptions.NoRecordsFound(
                    f"No exported DICOM RT plans found for Patient ID {patient_id} "
                    f"within the directory {monaco_export_directory}"
                )
            )
            return {"patient_id": patient_id}

        if len(dicom_plan_options) == 1:
            selected_plan = dicom_plan_options[0]
        else:
            selected_plan = st.radio(
                "Select DICOM Plan",
                dicom_plan_options,
                key=f"{key_namespace}_select_monaco_export_plan",
            )

        st.write(f"DICOM file being used: `{selected_plan}`")

        dicom_plan = dicom_plans[selected_plan]
        data_paths = [monaco_export_directory.joinpath(selected_plan)]

    patient_id = str(dicom_plan.PatientID)
    st.write(f"Patient ID: `{patient_id}`")

    patient_name = str(dicom_plan.PatientName)
    patient_name = utl_patient.convert_patient_name(patient_name)

    st.write(f"Patient Name: `{patient_name}`")

    rt_plan_name = str(dicom_plan.RTPlanName)
    st.write(f"Plan Name: `{rt_plan_name}`")

    try:
        deliveries_all_fractions = pymedphys.Delivery.from_dicom(
            dicom_plan, fraction_group_number="all"
        )
    except AttributeError:
        st.write(_exceptions.WrongFileType("Does not appear to be a photon DICOM plan"))
        return {}
    except ValueError as e:
        st.warning(
            """While extracting the delivery information out of the
            DICOM file the following error occurred
            """
        )

        st.write(e)
        st.stop()

    fraction_groups = list(deliveries_all_fractions.keys())
    if len(fraction_groups) == 1:
        delivery = deliveries_all_fractions[fraction_groups[0]]
    else:
        fraction_group_choices = {}

        for fraction, delivery in deliveries_all_fractions.items():
            rounded_mu = round(delivery.mu[-1], 1)

            fraction_group_choices[
                f"Perscription {fraction} with {rounded_mu} MU"
            ] = fraction

        fraction_group_selection = st.radio(
            "Select relevant perscription",
            list(fraction_group_choices.keys()),
            key=f"{key_namespace}_dicom_perscription_chooser",
        )

        fraction_group_number = fraction_group_choices[fraction_group_selection]
        delivery = deliveries_all_fractions[fraction_group_number]

    deliveries = [delivery]

    identifier = f"DICOM ({rt_plan_name})"

    return {
        "site": monaco_site,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": data_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }
