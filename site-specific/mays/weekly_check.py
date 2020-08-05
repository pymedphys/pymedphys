import os

import streamlit as st

import pandas as pd

from compare import color_results, compare_to_mosaiq
from helpers import get_all_dicom_treatment_info
from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_all_treatment_data, get_staff_initials
from tolerance_constants import SITE_CONSTANTS, TOLERANCE_TYPES

currdir = os.getcwd()

st.title("Weekly Check")

mrn = 1
mrn = st.text_input("Patient MRN: ")

if len(mrn) is not 0:
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        mosaiq_table = get_all_treatment_data(cursor, mrn)

    st.write(mosaiq_table)
    # display_results = compare_to_mosaiq(mosaiq_table, mosaiq_table)
    # st.write(display_results)
