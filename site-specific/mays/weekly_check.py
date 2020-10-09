import os

import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from datetime import date, timedelta

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import (
    get_all_treatment_history_data,
    get_incomplete_qcls,
    get_all_treatment_data,
)

currdir = os.getcwd()

st.title("Weekly Check")

mrn = st.text_input("Patient MRN: ")


def show_incomplete_weekly_checks():
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        incomplete_qcls = get_incomplete_qcls(cursor, "Physics Resident")
        # todays_date = date.today()
        # todays_date = todays_date.strftime('%b %d, %Y')
        todays_date = "Oct 12, 2020"
        incomplete_qcls = incomplete_qcls[
            (incomplete_qcls["task"] == "Weekly Chart Check")
            & (incomplete_qcls["due"] == todays_date)
        ]
        incomplete_qcls = incomplete_qcls.drop(columns=["instructions", "task", "due"])
        incomplete_qcls = incomplete_qcls.reset_index(drop=True)

    return incomplete_qcls


def compare_delivered_to_planned(patient):
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        planned_values = get_all_treatment_data(cursor, patient)
        delivered_values = get_all_treatment_history_data(cursor, patient)
        patient_results = pd.DataFrame()
        try:
            current_fx = max(delivered_values["fraction"])
            todays_date = date.today()
            week_ago = timedelta(days=7)
            delivered_values = delivered_values[
                delivered_values["date"] > todays_date - week_ago
            ]
            # delivered_values = delivered_values[
            #     delivered_values["fraction"] > current_fx - 5
            # ]
        except:
            print("fraction field empty")

        primary_checks = {
            "patient_id": patient,
            "was_verified": "",
            "partial_treatment": "",
            "was_overridden": "",
            "new_field": "",
        }

        if False in delivered_values["was_verified"].values:
            primary_checks["was_verified"] = "Unverified Treatment"

        if True in delivered_values["partial_treatment"].values:
            primary_checks["partial_treatment"] = "Partial Treatment"

        if True in delivered_values["was_overridden"].values:
            primary_checks["was_overridden"] = "Treatment Overridden"

        if True in delivered_values["new_field"].values:
            primary_checks["new_field"] = "New Field Delivered"

        for check in primary_checks.keys():
            patient_results[check] = [primary_checks[check]]

    return planned_values, delivered_values, patient_results


def compare_all_incompletes(incomplete_qcls):
    overall_results = pd.DataFrame()
    if not incomplete_qcls.empty:
        for patient in incomplete_qcls["patient_id"]:
            patient_results = pd.DataFrame()
            planned_values, delivered_values, patient_results = compare_delivered_to_planned(
                patient
            )
            # st.write(primary_checks)
            overall_results = overall_results.append(patient_results)
        st.write(len(incomplete_qcls))
        st.write(overall_results)
        return planned_values, delivered_values, overall_results

    else:
        return "No weeklys due today.", "Carry on."


if st.checkbox("Show incomplete QCLs"):
    incomplete_qcls = show_incomplete_weekly_checks()
    planned, delivered, overall_results = compare_all_incompletes(incomplete_qcls)
    st.write(show_incomplete_weekly_checks())
    # st.write(planned)
    # st.write(delivered)

    # if not incomplete_qcls.empty:
    #     st.write(
    #         planned[
    #             (planned["site_ID"] == 95444)
    #             & (planned["field_id"] == 478694)
    #             & (planned["site_setup_ID"] == 25823)
    #         ]
    #     )
if len(mrn) is not 0:
    planned, delivered, patient_results = compare_delivered_to_planned(mrn)
    # with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
    #     mosaiq_table = get_all_treatment_history_data(cursor, mrn)
    #     current_fx = max(mosaiq_table["fraction"])
    #     mosaiq_table = mosaiq_table[mosaiq_table["fraction"] > current_fx - 5]
    #
    # # st.write(compare_delivered_to_planned(incomplete_qcls))
    # st.write(mosaiq_table)

    # plot the couch coordinates for each delivered beam
    st.write(delivered)
    plt.scatter(
        delivered["couch_vrt"].index,
        delivered["couch_vrt"].values,
        label="couch_vrt",
        marker=".",
    )
    plt.scatter(
        delivered["couch_lat"].index,
        delivered["couch_lat"].values,
        label="couch_lat",
        marker=".",
    )
    plt.scatter(
        delivered["couch_lng"].index,
        delivered["couch_lng"].values,
        label="couch_lng",
        marker=".",
    )
    plt.title("Couch Positions for Each Beam On")
    plt.legend()
    st.pyplot()
