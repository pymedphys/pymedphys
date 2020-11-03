# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import pathlib

import streamlit as st

from . import exceptions, misc


def monaco_patient_directory_picker(
    patient_id="", key_namespace="", advanced_mode_local=False, site=None
):
    monaco_site, monaco_directory = misc.get_site_and_directory(
        "Monaco Plan Location",
        "monaco",
        default=site,
        key=f"{key_namespace}_monaco_site",
    )

    if advanced_mode_local:
        st.write(monaco_directory.resolve())

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    if advanced_mode_local:
        patient_id

    if patient_id == "":
        st.stop()

    plan_directories = list(monaco_directory.glob(f"*~{patient_id}/plan"))
    if len(plan_directories) == 0:
        if patient_id != "":
            st.write(
                exceptions.NoRecordsFound(
                    f"No Monaco plan directories found for patient ID {patient_id}"
                )
            )
            st.stop()

        return {"patient_id": patient_id}
    elif len(plan_directories) > 1:
        raise ValueError(
            "More than one patient plan directory found for this ID, "
            "please only have one directory per patient. "
            "Directories found were "
            f"{', '.join([str(path.resolve()) for path in plan_directories])}"
        )

    plan_directory = plan_directories[0]
    patient_directory = pathlib.Path(plan_directory).parent

    return monaco_site, monaco_directory, patient_id, plan_directory, patient_directory
