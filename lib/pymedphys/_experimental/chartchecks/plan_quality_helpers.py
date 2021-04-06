# Copyright (C) 2021 Jacob Rembish

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
from pymedphys._imports import streamlit as st

from pymedphys._experimental.chartchecks.dvh_helpers import (
    calc_reference_isodose_volume,
)
from pymedphys._experimental.chartchecks.helpers import add_new_structure_alias


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
    structure_df = calculate_average_oar_score(structure_df)
    # structure_df = pd.concat([structure_df, added_constraint]).reset_index(drop=True)
    return structure_df


def calculate_average_oar_score(structure_df):
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
    else:
        institutional_history = institutional_history[
            (institutional_history["site_id"] != constraints_df["site_id"].unique()[0])
            & (institutional_history["mrn"] != constraints_df["mrn"].unique()[0])
        ]
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
    d_95 = dvh_calcs[target].dose_constraint(95).value
    d_5 = dvh_calcs[target].dose_constraint(5).value
    dhi = d_95 / d_5
    return dhi


def perform_target_evaluation(dd_input, dvh_calcs):
    rois = list(dvh_calcs.keys())
    target = st.selectbox("Select the target structure: ", rois)
    rx_dose = st.number_input("Input Rx dose in Gy: ")

    min_dose = dvh_calcs[target].min
    max_dose = dvh_calcs[target].max
    mean_dose = dvh_calcs[target].mean

    if rx_dose != 0:
        d_1 = dvh_calcs[target].dose_constraint(1).value
        d_2 = dvh_calcs[target].dose_constraint(2).value
        d_98 = dvh_calcs[target].dose_constraint(98).value
        d_99 = dvh_calcs[target].dose_constraint(99).value
        conformity_index = calc_conformity_index(dd_input, dvh_calcs, target, rx_dose)
        homogeneity_index = calc_homogeneity_index(dvh_calcs, target, rx_dose)
        dhi = calc_dose_homogeneity_index(dvh_calcs, target)

        data = {
            "Min [Gy]": min_dose,
            "Max [Gy]": max_dose,
            "Mean [Gy]": mean_dose,
            "D1 [Gy]": d_1,
            "D2 [Gy]": d_2,
            "D98 [Gy]": d_98,
            "D99 [Gy]": d_99,
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


def compare_to_historical_scores(constraints_df, institutional_history, treatment_site):
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
                & (institutional_history["site"] == treatment_site)
            ]["Score"].mean()
        )

    df.loc[df["Type"] == "Total Score", "Institutional Average"] = df[
        df["Type"] == "Average Score"
    ]["Institutional Average"].sum()
    return df


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


def define_treatment_site():
    sites = [
        "<UNDEFINED>",
        "ABDOMEN",
        "BRAIN",
        "BREAST",
        "EXTREMITY",
        "H&N",
        "PELVIS - MALE",
        "PELVIS - FEMALE",
        "SPINE",
        "THORAX",
        "OTHER",
    ]

    selected_site = st.selectbox("Select the treatment site for this patient: ", sites)

    return selected_site
