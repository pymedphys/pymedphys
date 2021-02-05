from typing import BinaryIO, List, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st
from pymedphys._imports.plotly import graph_objects as go
from pymedphys._imports.plotly import subplots

from pymedphys._dicom.coords import coords_from_xyz_axes, xyz_axes_from_dataset
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

    axes = xyz_axes_from_dataset(ds, coord_system="FIXED")
    dose = dose_from_dataset(ds)
    dose_max = np.max(dose)
    idx_max = np.unravel_index(np.argmax(dose), dose.shape)

    fig = _initialise_figure()
    _update_fig_doses(fig, idx_max, axes, dose, dose_max)

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


def _update_fig_doses(fig, idx, axes, dose, dose_max):

    coords = coords_from_xyz_axes(axes)

    z_str = "{:.2f}".format(idx[0])
    hover_str_transverse = (
        "Dose (Gy):  %{z:.2f}<br />"
        + "x (mm):  %{x:.2f}<br />"
        + "y (mm):  %{y:.2f}<br />"
        + "z (mm):  "
        + z_str
    )

    x_str = "{:.2f}".format(idx[1])
    hover_str_sagittal = (
        "Dose (Gy):  %{z:.2f}<br />"
        + "x (mm):  "
        + x_str
        + "<br />"
        + "y (mm):  %{x:.2f}<br />"
        + "z (mm):  %{y:.2f}<br />"
    )

    y_str = "{:.2f}".format(idx[1])
    hover_str_coronal = (
        "Dose (Gy):  %{z:.2f}<br />"
        + "x (mm):  %{x:.2f}<br />"
        + "y (mm):  "
        + y_str
        + "<br />"
        + "z (mm):  %{y:.2f}<br />"
    )

    # Transverse
    fig.add_trace(
        go.Heatmap(
            colorbar=dict(title="Dose (Gy)"),
            colorscale="Jet",
            connectgaps=False,
            hovertemplate=hover_str_transverse,
            name="Dose",
            visible=True,
            x=axes[0],
            xaxis="x",
            y=axes[1],
            yaxis="y",
            z=dose[idx[0], :, :],
            zsmooth=False,
            zmin=0,
            zmax=dose_max,
        ),
        row=1,
        col=1,
    )

    # Sagittal
    fig.add_trace(
        go.Heatmap(
            colorbar=dict(title="Dose (Gy)"),
            colorscale="Jet",
            connectgaps=False,
            hovertemplate=hover_str_sagittal,
            name="Dose",
            visible=True,
            x=axes[2],
            xaxis="x",
            y=axes[1],
            yaxis="y",
            z=dose[:, :, idx[2]].T,
            zsmooth=False,
            zmin=0,
            zmax=dose_max,
        ),
        row=1,
        col=2,
    )

    # Coronal
    fig.add_trace(
        go.Heatmap(
            colorbar=dict(title="Dose (Gy)"),
            colorscale="Jet",
            connectgaps=False,
            hovertemplate=hover_str_coronal,
            name="Dose",
            visible=True,
            x=axes[0],
            xaxis="x",
            y=axes[2],
            yaxis="y",
            z=dose[:, idx[1], :],
            zsmooth=False,
            zmin=0,
            zmax=dose_max,
        ),
        row=2,
        col=1,
    )


def _initialise_figure():

    fig = subplots.make_subplots(
        rows=2,
        cols=2,
        vertical_spacing=0.1,
        subplot_titles=(
            "Transverse",
            "Sagittal",
            "Coronal",
            "Data",
        ),
    )
    fig.update_layout(
        xaxis=dict(),
        yaxis=dict(scaleanchor="x", scaleratio=1),
        xaxis2=dict(scaleanchor="x", scaleratio=1),
        yaxis2=dict(scaleanchor="y", scaleratio=1),
        xaxis3=dict(scaleanchor="x", scaleratio=1),
        yaxis3=dict(scaleanchor="y", scaleratio=1),
        paper_bgcolor="LightSteelBlue",
        height=600,
        width=800,
    )

    fig.update_yaxes(autorange="reversed", row=1)
    fig["layout"].update(margin=dict(l=5, r=5, b=5, t=30, pad=0))

    return fig
