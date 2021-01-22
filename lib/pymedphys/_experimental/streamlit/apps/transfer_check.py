# Copyright (C) 2020 Jacob Rembish

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

from pymedphys._mosaiq import connect
from pymedphys._streamlit import categories

from pymedphys._experimental.chartchecks.compare import (
    colour_results,
    compare_to_mosaiq,
)
from pymedphys._experimental.chartchecks.dvh_helpers import plot_dvh
from pymedphys._experimental.chartchecks.helpers import (
    get_all_dicom_treatment_info,
    get_all_treatment_data,
    get_staff_initials,
)
from pymedphys._experimental.chartchecks.tolerance_constants import (
    SITE_CONSTANTS,
    TOLERANCE_TYPES,
)

CATEGORY = categories.PRE_ALPHA
TITLE = "Pre-Treatment Data Transfer Check"


def main():
    server = "PRDMOSAIQIWVV01.utmsa.local"

    st.sidebar.header("Instructions:")
    st.sidebar.markdown(
        """
    To use this application, you must have the RP file of the plan you want to check. This can be exported in Pinnacle.
    You will get an error if you select a QA RP file.

    When exporting the DICOM, only the RP is needed. Once you have that, you can select it where prompted and the application
    will run.
    """
    )

    # Select patient DICOM files for pre-treatment check. Multiple files can be selected.
    dicomFiles = st.file_uploader(
        "Please select a RP file.", accept_multiple_files=True
    )

    # Create a structure to identify different types of DICOM files.
    files = {}
    for dicomFile in dicomFiles:
        name = dicomFile.name
        if "RP" in name:
            files["rp"] = dicomFile
        elif "RD" in name:
            files["rd"] = dicomFile
        elif "RS" in name:
            files["rs"] = dicomFile
        elif "CT" in name:
            files["ct"] = dicomFile
        else:
            continue

    # If an RP was selected, get plan information from both systems
    if "rp" in files:

        # Create a dataframe of plan information from DICOM RP file
        try:
            dicom_table = get_all_dicom_treatment_info(files["rp"])
            dicom_table["tolerance"] = [
                TOLERANCE_TYPES[item] for item in dicom_table["tolerance"]
            ]
            dicom_table = dicom_table.sort_values(["field_label"])
        except (AttributeError):
            st.write("Please select a new RP file.")
            st.stop()

        # Using MRN from RP file, find patient in MOSAIQ and perform query
        mrn = dicom_table.iloc[0]["mrn"]
        with connect.connect(server) as cursor:
            mosaiq_table = get_all_treatment_data(cursor, mrn)

            if mosaiq_table.iloc[0]["create_id"] is not None:
                try:
                    site_initials = get_staff_initials(
                        cursor, str(int(mosaiq_table.iloc[0]["create_id"]))
                    )
                except (TypeError, ValueError, AttributeError):
                    site_initials = ""

        # Limit MOSAIQ results to only the most current site and field versions for comparison
        mosaiq_table = mosaiq_table[
            (mosaiq_table["site_version"] == 0)
            & (mosaiq_table["site_setup_version"] == 0)
            & (mosaiq_table["field_version"] == 0)
        ]

        # Reset index and assign tolerance labels
        mosaiq_table = mosaiq_table.reset_index(drop=True)
        mosaiq_table["tolerance"] = [
            TOLERANCE_TYPES[item] for item in mosaiq_table["tolerance"]
        ]

        ####################################################################################################################
        # Verify general patient information between the two systems (name, MRN, DOB)
        st.subheader("Patient:")
        name = (
            dicom_table.iloc[0]["first_name"] + " " + dicom_table.iloc[0]["last_name"]
        )

        # Compare name between DICOM and MOSAIQ and write results
        if (
            name
            == mosaiq_table.iloc[0]["first_name"]
            + " "
            + mosaiq_table.iloc[0]["last_name"]
        ):
            st.success("Name: " + name)
        else:
            st.error("Name: " + name)

        # Compare MRN between DICOM and MOSAIQ and write results
        if mrn == mosaiq_table.iloc[0]["mrn"]:
            st.success("MRN: " + mrn)
        else:
            st.error("MRN: " + mrn)

        # Format DOB and compare between DICOM and MOSAIQ and write results
        DOB = str(mosaiq_table.iloc[0]["dob"])[0:10]
        dicom_DOB = dicom_table.iloc[0]["dob"]
        if DOB == dicom_DOB[0:4] + "-" + dicom_DOB[4:6] + "-" + dicom_DOB[6:8]:
            st.success("DOB: " + DOB)
        else:
            st.error("DOB: " + DOB)

        ####################################################################################################################
        # Section for checking approval statuses
        st.subheader("Approval Status:")

        # Check site setup approval
        if all(i == 5 for i in mosaiq_table.iloc[:]["site_setup_status"]):
            st.success("Site Setup Approved")
        else:
            for i in mosaiq_table.iloc[:]["site_setup_status"]:
                if i != 5:
                    st.error("Site Setup " + SITE_CONSTANTS[i])
                    break

        # Check site approval
        if all(i == 5 for i in mosaiq_table.iloc[:]["site_status"]):
            st.success("RX Approved by " + str(site_initials[0][0]))
        else:
            st.error("RX Approval Pending")

        ####################################################################################################################
        # Compare between DICOM and MOSAIQ

        # Create a list of all the fields within the DICOM RP file
        index = []
        for j in dicom_table.iloc[:]["field_label"]:
            for i in range(len(mosaiq_table)):
                if mosaiq_table.iloc[i]["field_label"] == j:
                    index.append(i)

        # Create a list of indices which contain fields not within the RP file
        remove = []
        for i in mosaiq_table.iloc[:].index:
            if i not in index:
                remove.append(i)

        # Drop all indices in the remove list to get rid of fields irrelevant for this comparison
        mosaiq_table = mosaiq_table.drop(remove)
        mosaiq_table = mosaiq_table.sort_index(axis=1)
        mosaiq_table = mosaiq_table.sort_values(by=["field_label"])

        # Compare values between the two systems and create a new dataframe with the results
        results = compare_to_mosaiq(dicom_table, mosaiq_table)
        results = results.transpose()

        # Create a radio selection of prescriptions in mosaiq to choose from for displaying results
        rx_selection = st.radio("Select RX: ", mosaiq_table.site.unique())
        rx_fields = mosaiq_table[mosaiq_table["site"] == rx_selection][
            "field_name"
        ].values

        # create a radio selection of fields to compare, only fields within selected rx appear as choices
        field_selection = st.radio("Select field to compare:", rx_fields)
        st.subheader("Comparison")

        # If a field is selected, write a side by side comparison of the DICOM and MOSAIQ plan information
        if len(field_selection) != 0:

            # Write prescription listed in the RP file
            st.write("**RX**: ", results[field_selection + "_DICOM"]["rx"])

            # Check if field has been approved, print initials of whoever approved
            try:
                field_approval_id = mosaiq_table[
                    mosaiq_table["field_name"] == field_selection
                ]["field_approval"]
                with connect.connect(server) as cursor:
                    field_approval_initials = get_staff_initials(
                        cursor, str(int(field_approval_id.iloc[0]))
                    )
                st.write("**Field Approved by: **", field_approval_initials[0][0])
            except (TypeError, ValueError, AttributeError):
                st.write("This field is not approved.")

            # Use radio field selection to format which fields to write from results dataframe
            dicom_field = str(field_selection) + "_DICOM"
            mosaiq_field = str(field_selection) + "_MOSAIQ"
            display_results = results[[dicom_field, mosaiq_field]]

            # Drop general patient info as it's already displayed above
            display_results = display_results.drop(
                ["dob", "first_name", "last_name", "mrn"], axis=0
            )

            # Format dataframe to color code results and then write the dataframe
            display_results = display_results.style.apply(colour_results, axis=1)
            st.dataframe(display_results.set_precision(2), height=1000)

            # Extract and write fractionation pattern from MOSAIQ for the specific field
            fx_pattern = mosaiq_table[mosaiq_table["field_name"] == field_selection][
                "fraction_pattern"
            ]
            st.write("**FX Pattern**: ", fx_pattern.iloc[0])

            # Extract and write comments from MOSAIQ for the specific field
            comments = mosaiq_table[mosaiq_table["field_name"] == field_selection][
                "notes"
            ]
            st.write("**Comments**: ", comments.iloc[0])

        # Create a checkbox to allow users to view all DICOM plan information
        show_dicom = st.checkbox("View complete DICOM table.")
        if show_dicom:
            st.subheader("DICOM Table")
            st.dataframe(dicom_table, height=1000)

        # Create a checkbox to allow users to view all MOSAIQ information
        show_mosaiq = st.checkbox("View complete Mosaiq table.")
        if show_mosaiq:
            st.subheader("Mosaiq Table")
            st.dataframe(mosaiq_table, height=1000)

        if "rs" in files and "rd" in files:
            show_dvh = st.checkbox("Create DVH Plot")
            if show_dvh:
                plot_dvh(files["rs"], files["rd"])
