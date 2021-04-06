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

from pymedphys._imports import pandas as pd
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as _mosaiq

from pymedphys._experimental.chartchecks.compare import (
    colour_results,
    compare_to_mosaiq,
    constraint_check_colour_results,
)
from pymedphys._experimental.chartchecks.dvh_helpers import calc_dvh, plot_dvh
from pymedphys._experimental.chartchecks.helpers import (
    get_all_dicom_treatment_data,
    get_all_mosaiq_treatment_data,
    get_staff_initials,
    get_structure_aliases,
)
from pymedphys._experimental.chartchecks.plan_quality_helpers import (
    add_alias,
    add_to_database,
    calculate_total_score,
    compare_structure_with_constraints,
    compare_to_historical_scores,
    define_treatment_site,
    perform_target_evaluation,
    point_to_isodose_rx,
)
from pymedphys._experimental.chartchecks.tolerance_constants import SITE_CONSTANTS

CATEGORY = categories.PRE_ALPHA
TITLE = "Pre-Treatment Data Transfer Check"


def main():
    config = st_config.get_config()
    st.write(config["chart_checks"]["archive_path"])
    connection = _mosaiq.get_single_mosaiq_connection_with_config(config)

    st.sidebar.header("Instructions:")
    st.sidebar.markdown(
        """
    To use this application, you must have the RP file of the plan you want to check. This can be exported in Pinnacle.
    You will get an error if you select a QA RP file.

    When exporting the DICOM, only the RP is needed for the data transfer check. Once you have that, you can select it where prompted and the application
    will run.

    To evaluate the DVH, you will need to import the RD and RS files as well.
    """
    )

    files = get_patient_files()
    if "rp" not in files:
        st.stop()

    try:
        dicom_table = get_all_dicom_treatment_data(files["rp"])
        dicom_table = dicom_table.sort_values(["field_label"])
    except AttributeError:
        st.write("Please select a new RP file.")
        st.stop()

    mrn = dicom_table.loc[0, "mrn"]
    mosaiq_table = get_all_mosaiq_treatment_data(connection, mrn)
    mosaiq_table = drop_irrelevant_mosaiq_fields(dicom_table, mosaiq_table)
    mosaiq_table = limit_mosaiq_data_to_current_versions(mosaiq_table)
    dicom_table = point_to_isodose_rx(dicom_table, mosaiq_table)
    verify_basic_patient_info(dicom_table, mosaiq_table, mrn)
    check_site_approval(mosaiq_table, connection)
    results = compare_to_mosaiq(dicom_table, mosaiq_table)
    results = results.transpose()

    (
        field_selection,
        selected_label,
        dicom_field_selection,
    ) = select_field_for_comparison(dicom_table, mosaiq_table)
    st.subheader("Comparison")
    if len(selected_label) != 0:
        show_field_rx(dicom_table, selected_label)
        check_for_field_approval(mosaiq_table, field_selection, connection)
        show_comparison_of_selected_fields(dicom_field_selection, results)
        show_fx_pattern_and_comments(mosaiq_table, field_selection)

    show_dicom(dicom_table)
    show_mosaiq(mosaiq_table)

    if "rs" not in files or "rd" not in files:
        st.stop()

    dd_input = files["rd"]
    ds_input = files["rs"]

    show_dvh = st.checkbox("Create DVH Plot")
    if show_dvh:
        dvh_calcs = calc_dvh(ds_input, dd_input)
        plot_dvh(dvh_calcs)

        treatment_site = define_treatment_site()
        institutional_history = pd.read_json(
            "P:/Share/AutoCheck/patient_archive.json"
        ).transpose()
        rois = dvh_calcs.keys()
        constraints = pd.read_json(
            "C:/Users/rembishj/pymedphys/lib/pymedphys/_experimental/chartchecks/dose_constraints.json"
        )
        constraints_df = pd.DataFrame()
        ALIASES = get_structure_aliases()
        for roi in rois:
            for structure in ALIASES.keys():
                if roi.lower().strip(" ") in ALIASES[structure].iloc[0]:
                    structure_df = compare_structure_with_constraints(
                        roi, structure, dvh_calcs, constraints=constraints
                    )
                    constraints_df = pd.concat(
                        [constraints_df, structure_df]
                    ).reset_index(drop=True)

        if constraints_df.empty is False:
            constraints_df = calculate_total_score(constraints_df)
            constraints_df["mrn"] = int(mrn)
            constraints_df["site_id"] = int(mosaiq_table.iloc[0]["site_ID"])
            constraints_df["site"] = treatment_site
            display_df = compare_to_historical_scores(
                constraints_df, institutional_history, treatment_site
            )
            display_df[display_df["Type"] == "Total Score"].iloc[0][
                "Institutional Average"
            ] = [
                display_df[display_df["Type"] == "Average Score"][
                    "Institutional Average"
                ].sum()
            ]

            display_df = display_df.style.apply(constraint_check_colour_results, axis=1)

            st.subheader("Constraint Check")
            st.dataframe(display_df.set_precision(2), height=1000)

        perform_target_evaluation(dd_input, dvh_calcs)

        add_alias(dvh_calcs, ALIASES)
        add_to_database(constraints_df, institutional_history)


def get_patient_files():
    dicomFiles = st.file_uploader(
        "Please select a RP file.", accept_multiple_files=True
    )

    files = {}
    for dicomFile in dicomFiles:
        read_file = pydicom.dcmread(dicomFile, force=True)
        dicom_type = read_file.Modality
        if dicom_type == "RTPLAN":
            files["rp"] = read_file
        elif dicom_type == "RTDOSE":
            files["rd"] = read_file
        elif dicom_type == "RTSTRUCT":
            files["rs"] = read_file
        elif dicom_type == "CT":
            files["ct"] = read_file
        else:
            continue
    return files


def limit_mosaiq_data_to_current_versions(mosaiq_treatment_data):
    mosaiq_treatment_data = mosaiq_treatment_data[
        (mosaiq_treatment_data["site_version"] == 0)
        & (mosaiq_treatment_data["site_setup_version"] == 0)
        & (mosaiq_treatment_data["field_version"] == 0)
    ]

    mosaiq_treatment_data = mosaiq_treatment_data.reset_index(drop=True)
    return mosaiq_treatment_data


def verify_basic_patient_info(dicom_table, mosaiq_table, mrn):
    st.subheader("Patient:")
    dicom_name = (
        dicom_table.loc[0, "first_name"] + " " + dicom_table.loc[0, "last_name"]
    )
    mosaiq_name = (
        mosaiq_table.loc[0, "first_name"] + " " + mosaiq_table.loc[0, "last_name"]
    )

    if dicom_name == mosaiq_name:
        st.success("Name: " + dicom_name)
    else:
        st.error("Name: " + dicom_name)

    if mrn == mosaiq_table.loc[0, "mrn"]:
        st.success("MRN: " + mrn)
    else:
        st.error("MRN: " + mrn)

    DOB = str(mosaiq_table.loc[0, "dob"])[0:10]
    dicom_DOB = dicom_table.loc[0, "dob"]
    if DOB == dicom_DOB[0:4] + "-" + dicom_DOB[4:6] + "-" + dicom_DOB[6:8]:
        st.success("DOB: " + DOB)
    else:
        st.error("DOB: " + DOB)


def check_site_approval(mosaiq_table, connection):
    st.subheader("Approval Status:")

    if mosaiq_table.loc[0, "create_id"] is not None:
        try:
            site_initials = get_staff_initials(
                connection, str(int(mosaiq_table.loc[0, "create_id"]))
            )
        except (TypeError, ValueError, AttributeError):
            site_initials = ""

    # Check site setup approval
    if all(i == 5 for i in mosaiq_table.loc[:, "site_setup_status"]):
        st.success("Site Setup Approved")
    else:
        for i in mosaiq_table.loc[:, "site_setup_status"]:
            if i != 5:
                st.error("Site Setup " + SITE_CONSTANTS[i])
                break

    # Check site approval
    if all(i == 5 for i in mosaiq_table.loc[:, "site_status"]):
        st.success("RX Approved by " + str(site_initials[0][0]))
    else:
        st.error("RX Approval Pending")


def drop_irrelevant_mosaiq_fields(dicom_table, mosaiq_table):
    index = []
    for j in dicom_table.loc[:, "field_label"]:
        for i in range(len(mosaiq_table)):
            if mosaiq_table.loc[i, "field_label"].lower() == j.lower():
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

    return mosaiq_table


def select_field_for_comparison(dicom_table, mosaiq_table):
    rx_selection = st.radio("Select RX: ", mosaiq_table.site.unique())
    rx_fields = mosaiq_table[mosaiq_table["site"] == rx_selection]["field_name"].values

    # create a radio selection of fields to compare, only fields within selected rx appear as choices
    field_selection = st.radio("Select field to compare:", rx_fields)
    selected_label = mosaiq_table[mosaiq_table["field_name"] == field_selection][
        "field_label"
    ]
    dicom_field_selection = dicom_table[
        dicom_table["field_label"] == selected_label.values[0]
    ]["field_name"].values[0]

    return field_selection, selected_label, dicom_field_selection


def check_for_field_approval(mosaiq_table, field_selection, connection):
    try:
        field_approval_id = mosaiq_table[mosaiq_table["field_name"] == field_selection][
            "field_approval"
        ]

        field_approval_initials = get_staff_initials(
            connection, str(int(field_approval_id.iloc[0]))
        )
        st.write("**Field Approved by: **", field_approval_initials[0][0])
    except (TypeError, ValueError, AttributeError):
        st.write("This field is not approved.")


def show_fx_pattern_and_comments(mosaiq_table, field_selection):
    fx_pattern = mosaiq_table[mosaiq_table["field_name"] == field_selection][
        "fraction_pattern"
    ]
    st.write("**FX Pattern**: ", fx_pattern.iloc[0])

    # Extract and write comments from MOSAIQ for the specific field
    comments = mosaiq_table[mosaiq_table["field_name"] == field_selection]["notes"]
    st.write("**Comments**: ", comments.iloc[0])


def show_field_rx(dicom_table, selected_label):
    st.write(
        "**RX**: ",
        dicom_table[dicom_table["field_label"] == selected_label.values[0]][
            "rx"
        ].values[0],
    )


def show_comparison_of_selected_fields(dicom_field_selection, results):
    dicom_field = str(dicom_field_selection) + "_DICOM"
    mosaiq_field = str(dicom_field_selection) + "_MOSAIQ"
    display_results = results[[dicom_field, mosaiq_field]]

    display_results = display_results.drop(
        ["dob", "first_name", "last_name", "mrn"], axis=0
    )

    display_results = display_results.style.apply(colour_results, axis=1)
    st.dataframe(display_results.set_precision(2), height=1000)


def show_dicom(dicom_table):
    show_table = st.checkbox("View complete DICOM table.")
    if show_table:
        st.subheader("DICOM Table")
        st.dataframe(dicom_table, height=1000)


def show_mosaiq(mosaiq_table):
    show_table = st.checkbox("View complete Mosaiq table.")
    if show_table:
        st.subheader("Mosaiq Table")
        st.dataframe(mosaiq_table, height=1000)
