from typing import BinaryIO, List, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st
from pymedphys._imports.plotly import graph_objects as go

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._dicom.utilities import pretty_patient_name
from pymedphys._streamlit import categories

CATEGORY = categories.PRE_ALPHA
TITLE = "Plot Dose from DICOM"


def main():
    left_column, right_column = st.beta_columns(2)

    with left_column:
        st.write("## Upload DICOM RT Dose files")
        file: BinaryIO = st.file_uploader(
            "Upload a DICOM RT Dose file whose dose you'd " "like to plot.",
            ["dcm"],
            accept_multiple_files=False,
        )

    if file is None:
        st.stop()

    try:
        ds = _load_rtdose_file(file)
    except ValueError as e:
        st.write(e)
        st.stop()

    with right_column:
        st.write(
            f"""

            ## Details

            * Patient ID: `{ds.PatientID}`
            * Patient Name: `{pretty_patient_name(ds)}`
            """
        )

    x, y, z = xyz_axes_from_dataset(ds)
    dose = dose_from_dataset(ds)
    dose_max = np.max(dose)

    fig = go.Figure()
    fig.update_yaxes(autorange="reversed")

    for zp, dose_slice in zip(z, dose):
        _add_dose_slice_to_fig(fig, x, y, zp, dose_slice, dose_max)

    st.plotly_chart(fig)


def _load_rtdose_file(fh: BinaryIO):
    try:
        ds = pydicom.dcmread(fh)
    except pydicom.errors.InvalidDicomError as e:
        raise ValueError(f"'{fh.name}' is not a valid DICOM file") from e

    try:
        _validate_dicom_dataset(ds)
    except ValueError:
        st.error(f"When trying to load {fh.name}, the following error occurred:")

        raise

    return ds


def _validate_dicom_dataset(ds):
    if ds.Modality != "RTDOSE":
        raise ValueError("DICOM dataset is not RT Dose")


def _add_dose_slice_to_fig(fig, x, y, z_slice, dose_slice, dose_max):
    z_slice_as_str = "{:.2f}".format(z_slice)
    hover_str = (
        "Dose (Gy):  %{z:.2f}<br />"
        + "x (mm):  %{x:.2f}<br />"
        + "y (mm):  %{y:.2f}<br />"
        + "z (mm):  "
        + z_slice_as_str
    )
    fig.add_trace(
        go.Heatmap(
            colorbar=dict(title="Dose (Gy)", x=1.05, y=0.85, len=0.4),
            colorscale="Jet",
            connectgaps=False,
            hovertemplate=hover_str,
            name="Dose",
            visible=False,
            x=x,
            xaxis="x",
            y=y,
            yaxis="y",
            z=dose_slice,
            zsmooth=False,
            zmin=0,
            zmax=dose_max,
        ),
    )
