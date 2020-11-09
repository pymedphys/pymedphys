from pymedphys._imports import dbfread
from pymedphys._imports import streamlit as st


@st.cache()
def get_dbf_table(path):
    try:
        return dbfread.DBF(path)
    except dbfread.DBFNotFound as e:
        raise FileNotFoundError(path) from e
