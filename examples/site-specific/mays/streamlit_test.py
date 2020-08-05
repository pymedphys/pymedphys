import io

# Insert progress bar
import time

import streamlit as st

import pandas as pd

from PIL import Image

import pydicom

from helpers import get_all_dicom_treatment_info

df = pd.DataFrame([1, 2, 3])
# Text/Title
st.title("Data Transfer Check")

# Header/Subheader
st.header("This is a header")
st.subheader("This is a subheader")

# Text
st.text("Hello Streamlit!")

# Markdown
st.markdown("This is a markdown")

# Error/Colorful Text
st.success("Successful")
st.info("Information!")
st.warning("WARNING")
st.exception("NameError('name three not defined')")

# Get help for any function
st.help(range)

# Writing text
st.write("Text using st.write")
st.write((range(10)))

# How to include dataframes into the GUI
st.write(df)

# How to include images
# img = Image.open('C:/Users/rembishj/git/pymedphys/docs/logos/UTHSA_logo.png')
# st.image(img)
# st.image(img, width=300, caption="UTHSCSA Logo")

# Include widgets
if st.checkbox("Show/Hide"):
    st.text("Showing or Hiding Widget")

# How to request file selection
file = st.file_uploader("Please select a file", encoding=None)
dicom_table = get_all_dicom_treatment_info(file)
st.write(dicom_table)
name = dicom_table.iloc[0]["first_name"] + " " + dicom_table.iloc[0]["last_name"]
st.subheader("Patient:")
st.write("Name: ", name)

mrn = dicom_table.iloc[0]["mrn"]
st.write("MRN: ", mrn)

# Select Box
occupation = st.selectbox(
    "Select your occupation:", ["janitor", "physicist", "unemployed"]
)
st.write("You are a ", occupation)

# Multiselect Box
occupation = st.multiselect(
    "Select your occupation:", ["janitor", "physicist", "unemployed"]
)
st.write("You are a ", occupation)

# Slider
age = st.slider("What is your age?", 0, 99)

# Buttons
st.button("Simple Button")
if st.button("About"):
    st.text("Streamlit is cool")

# Text input
name = st.text_input("What is your name?", "Insert name here...")

my_bar = st.progress(0)
for p in range(10):
    my_bar.progress(p + 1)
    p += 1

# Sidebars
st.sidebar.header("About")
st.sidebar.text("This is a test")

# Functions
@st.cache
def run_fxn():
    return range(100)


st.write(run_fxn())

# Plots
st.pyplot()
