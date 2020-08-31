import os

import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from datetime import date

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import (
    get_all_treatment_history_data,
    get_incomplete_qcls,
    get_all_treatment_data,
)

currdir = os.getcwd()

st.title("Weekly Check")

mrn = st.text_input("Patient MRN: ")


def compare_delivered_to_planned(incomplete_qcls):
    if not incomplete_qcls.empty:
        all_planned_values = pd.DataFrame()
        for patient in incomplete_qcls["patient_id"]:
            with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
                planned_values = get_all_treatment_data(cursor, patient)
                delivered_values = get_all_treatment_history_data(cursor, patient)
                current_fx = max(delivered_values["fraction"])
                delivered_values = delivered_values[
                    delivered_values["fraction"] > current_fx - 5
                ]
                all_planned_values = all_planned_values.append(planned_values)
        return planned_values, delivered_values

    else:
        return "No weeklys due today."


def show_incomplete_weekly_checks():
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        incomplete_qcls = get_incomplete_qcls(cursor, "Physics Resident")
        # todays_date = date.today()
        # todays_date = todays_date.strftime('%b %d, %Y')
        todays_date = "Sep 2, 2020"
        incomplete_qcls = incomplete_qcls[
            (incomplete_qcls["task"] == "Weekly Chart Check")
            & (incomplete_qcls["due"] == todays_date)
        ]
        incomplete_qcls = incomplete_qcls.reset_index(drop=True)

    return incomplete_qcls


incomplete_qcls = show_incomplete_weekly_checks()
planned, delivered = compare_delivered_to_planned(incomplete_qcls)
st.write(show_incomplete_weekly_checks())
st.write(planned)
st.write(delivered)

st.write(
    planned[
        (planned["site_ID"] == 96229)
        & (planned["field_id"] == 481036)
        & (planned["site_setup_ID"] == 26926)
    ]
)
if len(mrn) is not 0:
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        mosaiq_table = get_all_treatment_history_data(cursor, mrn)
        current_fx = max(mosaiq_table["fraction"])
        mosaiq_table = mosaiq_table[mosaiq_table["fraction"] > current_fx - 5]

    # st.write(compare_delivered_to_planned(incomplete_qcls))
    # st.write(mosaiq_table)

    # plot the couch coordinates for each delivered beam
    plt.plot(
        mosaiq_table["couch_vrt"].index,
        mosaiq_table["couch_vrt"].values,
        label="couch_vrt",
    )
    plt.plot(
        mosaiq_table["couch_lat"].index,
        mosaiq_table["couch_lat"].values,
        label="couch_lat",
    )
    plt.plot(
        mosaiq_table["couch_lng"].index,
        mosaiq_table["couch_lng"].values,
        label="couch_lng",
    )
    plt.title("Couch Positions for Each Beam On")
    plt.legend()
    st.pyplot()
