import os

import streamlit as st
import matplotlib.pyplot as plt
import numpy as np

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_all_treatment_history_data

currdir = os.getcwd()

st.title("Weekly Check")

mrn = st.text_input("Patient MRN: ")

if len(mrn) is not 0:
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        mosaiq_table = get_all_treatment_history_data(cursor, mrn)

    st.write(mosaiq_table)

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
