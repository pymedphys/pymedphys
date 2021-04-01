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

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities.mosaiq import get_cached_mosaiq_connection

from pymedphys._experimental.chartchecks.compare import (
    colour_results,
    compare_to_mosaiq,
    constraint_check_colour_results,
)
from pymedphys._experimental.chartchecks.dvh_helpers import (
    calc_dvh,
    calc_reference_isodose_volume,
    plot_dvh,
)
from pymedphys._experimental.chartchecks.helpers import (
    add_new_structure_alias,
    get_all_dicom_treatment_data,
    get_all_mosaiq_treatment_data,
    get_staff_initials,
    get_structure_aliases,
)
from pymedphys._experimental.chartchecks.tolerance_constants import SITE_CONSTANTS

CATEGORY = categories.PRE_ALPHA
TITLE = "Pre-Treatment Data Transfer Check"


def get_patient_files():
    dicomFiles = st.file_uploader(
        "Please select a RP file.", accept_multiple_files=True
    )

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


def compare_structure_with_constraints(roi, structure, dvh_calcs, constraints):
    structure_constraints = constraints[structure]
    structure_dvh = dvh_calcs[roi]
    structure_df = pd.DataFrame()
    for constraint_type, constraint in structure_constraints.items():
        if constraint_type == "Mean" and constraint != " ":
            for val in constraint:
                added_constraint = pd.DataFrame()
                added_constraint["Structure"] = [roi]
                added_constraint["Structure_Key"] = [structure]
                added_constraint["Type"] = ["Mean"]
                added_constraint["Dose [Gy]"] = [val[0]]
                added_constraint["Volume [%]"] = ["-"]
                added_constraint["Actual Dose [Gy]"] = structure_dvh.mean
                added_constraint["Actual Volume [%]"] = ["-"]
                added_constraint["Score"] = [val[0] - structure_dvh.mean]
                structure_df = pd.concat([structure_df, added_constraint]).reset_index(
                    drop=True
                )

        elif constraint_type == "Max" and constraint != " ":
            for val in constraint:
                added_constraint = pd.DataFrame()
                added_constraint["Structure"] = [roi]
                added_constraint["Structure_Key"] = [structure]
                added_constraint["Type"] = ["Max"]
                added_constraint["Dose [Gy]"] = [val[0]]
                added_constraint["Volume [%]"] = ["-"]
                added_constraint["Actual Dose [Gy]"] = structure_dvh.max
                added_constraint["Actual Volume [%]"] = ["-"]
                added_constraint["Score"] = [val[0] - structure_dvh.max]
                structure_df = pd.concat([structure_df, added_constraint]).reset_index(
                    drop=True
                )

        elif constraint_type == "V%" and constraint != " ":
            for val in constraint:
                dose_constraint = [val[0]]
                volume_constraint = [val[1] * 100]
                actual_dose = structure_dvh.dose_constraint(volume_constraint).value
                actual_volume = (
                    structure_dvh.volume_constraint(dose_constraint, "Gy").value
                    / structure_dvh.volume
                ) * 100
                added_constraint = pd.DataFrame()
                added_constraint["Structure"] = [roi]
                added_constraint["Structure_Key"] = [structure]
                added_constraint["Type"] = ["V%"]
                added_constraint["Dose [Gy]"] = dose_constraint
                added_constraint["Volume [%]"] = volume_constraint
                added_constraint["Actual Dose [Gy]"] = actual_dose
                added_constraint["Actual Volume [%]"] = actual_volume
                added_constraint["Score"] = (dose_constraint - actual_dose) + (
                    volume_constraint - actual_volume
                )
                structure_df = pd.concat([structure_df, added_constraint]).reset_index(
                    drop=True
                )

        elif constraint_type == "D%" and constraint != " ":
            for val in constraint:
                dose_constraint = [val[0]]
                volume_constraint = [val[1]]
                actual_dose = structure_dvh.dose_constraint(
                    volume_constraint, "cm3"
                ).value
                actual_volume = (
                    structure_dvh.volume_constraint(dose_constraint, "Gy").value
                    / structure_dvh.volume
                ) * 100
                added_constraint = pd.DataFrame()
                added_constraint["Structure"] = [roi]
                added_constraint["Structure_Key"] = [structure]
                added_constraint["Type"] = ["D%"]
                added_constraint["Dose [Gy]"] = dose_constraint
                added_constraint["Volume [%]"] = volume_constraint
                added_constraint["Actual Dose [Gy]"] = actual_dose
                added_constraint["Actual Volume [%]"] = actual_volume
                added_constraint["Score"] = (dose_constraint - actual_dose) + (
                    (volume_constraint / structure_dvh.volume) * 100 - actual_volume
                )
                structure_df = pd.concat([structure_df, added_constraint]).reset_index(
                    drop=True
                )
    structure_df = calculate_average_OAR_score(structure_df)
    # structure_df = pd.concat([structure_df, added_constraint]).reset_index(drop=True)
    return structure_df


def calculate_average_OAR_score(structure_df):
    average_oar_scores = pd.DataFrame()
    average_oar_scores["Structure"] = [structure_df.iloc[0]["Structure"]]
    average_oar_scores["Structure_Key"] = [structure_df.iloc[0]["Structure_Key"]]
    average_oar_scores["Type"] = ["Average Score"]
    average_oar_scores["Dose [Gy]"] = ["-"]
    average_oar_scores["Volume [%]"] = ["-"]
    average_oar_scores["Actual Dose [Gy]"] = ["-"]
    average_oar_scores["Actual Volume [%]"] = ["-"]
    average_oar_scores["Score"] = structure_df["Score"].mean()

    structure_df = pd.concat([structure_df, average_oar_scores]).reset_index(drop=True)
    # for structure in constraints_df['Structure'].unique():
    #     average_oar_scores[structure] = [constraints_df[constraints_df['Structure'] == structure].loc[:]['Score'].mean()]
    # st.write(average_oar_scores)
    return structure_df


def calculate_total_score(constraints_df):
    total_score = pd.DataFrame()
    total_score["Structure"] = ["Total Patient"]
    total_score["Structure_Key"] = ["Total Patient"]
    total_score["Type"] = ["Total Score"]
    total_score["Dose [Gy]"] = ["-"]
    total_score["Volume [%]"] = ["-"]
    total_score["Actual Dose [Gy]"] = ["-"]
    total_score["Actual Volume [%]"] = ["-"]
    total_score["Score"] = constraints_df[constraints_df["Type"] == "Average Score"][
        "Score"
    ].sum()

    constraints_df = pd.concat([constraints_df, total_score]).reset_index(drop=True)
    return constraints_df


def add_constraint_results_to_database(constraints_df, institutional_history):
    if (
        constraints_df["site_id"].unique()[0]
        not in institutional_history["site_id"].values
    ):
        institutional_history = pd.concat(
            [institutional_history, constraints_df]
        ).reset_index(drop=True)
        institutional_history.to_json(
            "P://Share/AutoCheck/patient_archive.json",
            orient="index",
            indent=4,
            double_precision=3,
        )


# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5672112/
def calc_conformity_index(dd_input, dvh_calcs, target, rx_dose):
    iso_100 = calc_reference_isodose_volume(dd_input, rx_dose)
    target_volume = dvh_calcs[target].volume
    conformity_index = iso_100 / target_volume
    return conformity_index


# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5672112/
def calc_homogeneity_index(dvh_calcs, target, rx_dose):
    max_target_dose = dvh_calcs[target].max
    homogeneity_index = max_target_dose / rx_dose
    return homogeneity_index


# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5672112/
def calc_dose_homogeneity_index(dvh_calcs, target):
    D_95 = dvh_calcs[target].dose_constraint(95).value
    D_5 = dvh_calcs[target].dose_constraint(5).value
    DHI = D_95 / D_5
    return DHI


def perform_target_evaluation(dd_input, dvh_calcs):
    rois = list(dvh_calcs.keys())
    target = st.selectbox("Select the target structure: ", rois)
    rx_dose = st.number_input("Input Rx dose in Gy: ")

    min_dose = dvh_calcs[target].min
    max_dose = dvh_calcs[target].max
    mean_dose = dvh_calcs[target].mean

    if rx_dose != 0:
        D_1 = dvh_calcs[target].dose_constraint(1).value
        D_2 = dvh_calcs[target].dose_constraint(2).value
        D_98 = dvh_calcs[target].dose_constraint(98).value
        D_99 = dvh_calcs[target].dose_constraint(99).value
        conformity_index = calc_conformity_index(dd_input, dvh_calcs, target, rx_dose)
        homogeneity_index = calc_homogeneity_index(dvh_calcs, target, rx_dose)
        dhi = calc_dose_homogeneity_index(dvh_calcs, target)

        data = {
            "Min [Gy]": min_dose,
            "Max [Gy]": max_dose,
            "Mean [Gy]": mean_dose,
            "D1 [Gy]": D_1,
            "D2 [Gy]": D_2,
            "D98 [Gy]": D_98,
            "D99 [Gy]": D_99,
            "CI": conformity_index,
            "HI": homogeneity_index,
            "DHI": dhi,
        }

        target_df = pd.DataFrame.from_dict(
            data, orient="Index", columns=[target]
        ).style.set_precision(2)

    else:
        target_df = pd.DataFrame()

    return st.write(target_df)


def compare_to_historical_scores(constraints_df, institutional_history):
    df = constraints_df.copy()
    df = df.replace(np.nan, "-")
    df["Institutional Average"] = np.nan
    for index in df.index:
        row_key = df["Structure_Key"][index]
        row_type = df["Type"][index]
        row_dose = df["Dose [Gy]"][index]
        row_volume = df["Volume [%]"][index]

        if not isinstance(row_dose, str):
            row_dose = np.round(row_dose)

        if not isinstance(row_volume, str):
            row_volume = np.round(row_volume)

        df["Institutional Average"][index] = float(
            institutional_history[
                (institutional_history["Structure_Key"] == row_key)
                & (institutional_history["Type"] == row_type)
                & (institutional_history["Dose [Gy]"] == row_dose)
                & (institutional_history["Volume [%]"] == row_volume)
            ]["Score"].mean()
        )

    df.loc[df["Type"] == "Total Score", "Institutional Average"] = df[
        df["Type"] == "Average Score"
    ]["Institutional Average"].sum()
    return df


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


def add_alias(dvh_calcs, aliases):
    define_alias = st.checkbox("Define a new structure alias")
    if define_alias:
        add_new_structure_alias(dvh_calcs, aliases)


def add_to_database(constraints_df, institutional_history):
    add_to = st.checkbox("Add patient to Database")
    if add_to:
        add_constraint_results_to_database(constraints_df, institutional_history)


def point_to_isodose_rx(dicom_table, mosaiq_table):
    for index, field in dicom_table.iterrows():
        if "point dose" in field.loc["rx"]:
            normalize_to = float(
                mosaiq_table.loc[
                    mosaiq_table["field_label"] == field.loc["field_label"]
                ]
                .reset_index()
                .at[0, "rx_depth"]
                / 100
            )
            dicom_table.at[index, "fraction_dose [cGy]"] = np.round(
                field.at["fraction_dose [cGy]"] * normalize_to
            )
            dicom_table.at[index, "total_dose [cGy]"] = np.round(
                field.at["total_dose [cGy]"] * normalize_to
            )
    return dicom_table


def main():
    server = "PRDMOSAIQIWVV01.utmsa.local"
    connection = get_cached_mosaiq_connection(server)

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

    dd_input: pydicom.FileDataset = pydicom.dcmread(files["rd"], force=True)
    ds_input: pydicom.FileDataset = pydicom.dcmread(files["rs"], force=True)

    show_dvh = st.checkbox("Create DVH Plot")
    if show_dvh:
        dvh_calcs = calc_dvh(ds_input, dd_input)
        plot_dvh(dvh_calcs)

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
            display_df = compare_to_historical_scores(
                constraints_df, institutional_history
            )
            display_df[display_df["Type"] == "Total Score"].iloc[0][
                "Institutional Average"
            ] = [
                display_df[display_df["Type"] == "Average Score"][
                    "Institutional Average"
                ].sum()
            ]

            display_df = display_df.style.apply(constraint_check_colour_results, axis=1)

            # constraints_df.set_properties(subset=["Structure"], **{'align': 'center'})
            st.subheader("Constraint Check")
            st.dataframe(display_df.set_precision(2), height=1000)

        perform_target_evaluation(dd_input, dvh_calcs)

        add_alias(dvh_calcs, ALIASES)
        add_to_database(constraints_df, institutional_history)
