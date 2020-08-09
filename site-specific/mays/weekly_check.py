import os

import streamlit as st

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_all_treatment_data

currdir = os.getcwd()

st.title("Weekly Check")

mrn = st.text_input("Patient MRN: ")

if len(mrn) is not 0:
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        mosaiq_table = get_all_treatment_data(cursor, mrn)

    st.write(mosaiq_table)
    # display_results = compare_to_mosaiq(mosaiq_table, mosaiq_table)
    # st.write(display_results)
