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

    axes_fixed = xyz_axes_from_dataset(ds, coord_system="FIXED")
    axes_pat = xyz_axes_from_dataset(ds, coord_system="IEC PATIENT")
    axes_dicom = xyz_axes_from_dataset(ds, coord_system="DICOM")

    st.write(f"Fixed X: {axes_fixed[0][0]} to {axes_fixed[0][-1]}")
    st.write(f"Patient X: {axes_pat[0][0]} to {axes_pat[0][-1]}")
    st.write(f"DICOM X: {axes_dicom[0][0]} to {axes_dicom[0][-1]}")
    st.write(f"Fixed Y: {axes_fixed[1][0]} to {axes_fixed[1][-1]}")
    st.write(f"Patient Y: {axes_pat[1][0]} to {axes_pat[1][-1]}")
    st.write(f"DICOM Y: {axes_dicom[1][0]} to {axes_dicom[1][-1]}")
    st.write(f"Fixed Z: {axes_fixed[2][0]} to {axes_fixed[2][-1]}")
    st.write(f"Patient Z: {axes_pat[2][0]} to {axes_pat[2][-1]}")
    st.write(f"DICOM Z: {axes_dicom[2][0]} to {axes_dicom[2][-1]}")

    # assert np.array_equal(axes_dicom[0], axes_pat[0])
    # assert np.array_equal(axes_dicom[1], -axes_pat[2])
    # assert np.array_equal(axes_dicom[2], axes_pat[1])

    # assert np.array_equal(axes_pat[0], -axes_fixed[2])
    # assert np.array_equal(axes_pat[1], -axes_fixed[1])
    # assert np.array_equal(axes_pat[2], -axes_fixed[0])

    dose = dose_from_dataset(ds)

    fig = _initialise_figure()
    _update_fig_doses(fig, axes_fixed, dose)

    st.plotly_chart(fig)


def _load_rtdose_file(fh: BinaryIO):
    try:
        ds = pydicom.dcmread(fh)
    except pydicom.errors.InvalidDicomError as e:
        raise ValueError(f"'{fh.name}' is not a valid DICOM file") from e

    if ds.Modality != "RTDOSE":
        raise ValueError("DICOM dataset is not RT Dose")

    return ds


def _generate_hover_str(anatomical_plane, point):

    if anatomical_plane.lower() in ("transverse", "t"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + "x (mm):  %{x:.2f}<br />"
            + f"y (mm):  {point[1]:.2f}<br />"
            + "z (mm):  %{y:.2f}"
        )
    elif anatomical_plane.lower() in ("sagittal", "s"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + f"x (mm):  {point[0]:.2f}<br />"
            + "y (mm):  %{x:.2f}<br />"
            + "z (mm):  %{y:.2f}"
        )
    elif anatomical_plane.lower() in ("coronal", "c"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + "x (mm):   %{x:.2f}<br />"
            + "y (mm):  %{y:.2f}<br />"
            + f"z (mm):  {point[2]:.2f}"
        )

    return hover_str


def _generate_heatmap(axes, dose, idx, anatomical_plane, norm_dose="max_all"):

    xp, yp, zp = _get_point_at_idx(idx, axes)

    if anatomical_plane.lower() in ("transverse", "t"):
        abscissa = axes[0]
        ordinate = axes[2]
        dose_slice = dose[idx[0], :, :]
    elif anatomical_plane.lower() in ("sagittal", "s"):
        abscissa = axes[1]
        ordinate = axes[2]
        dose_slice = np.rot90(dose[:, :, idx[2]], k=3)
    elif anatomical_plane.lower() in ("coronal", "c"):
        abscissa = axes[0]
        ordinate = axes[1]
        dose_slice = dose[:, idx[1], :]
    else:
        raise ValueError("Invalid value for `anatomical_plane`.")

    if norm_dose.lower() == "max_all":
        norm_dose_val = np.max(dose)
    elif norm_dose.lower() == "max_slice":
        norm_dose_val = np.max(dose_slice)
    else:
        raise ValueError("Invalid value for `norm_dose`.")

    return go.Heatmap(
        colorbar=dict(title="Dose (Gy)"),
        colorscale="Jet",
        connectgaps=False,
        hovertemplate=_generate_hover_str(anatomical_plane, (xp, yp, zp)),
        name="Dose",
        visible=True,
        x=abscissa,
        xaxis="x",
        y=ordinate,
        yaxis="y",
        z=dose_slice,
        zsmooth=False,
        zmin=0,
        zmax=norm_dose_val,
    )


def _get_point_at_idx(idx, axes):
    return (
        axes[0][idx[2]],
        axes[1][idx[0]],
        axes[2][idx[1]],
    )


def update_fig(trace, points, selector):
    st.write(trace)
    st.write(points)
    st.write(selector)


def _update_fig_doses(fig, axes, dose, idx=None):
    # Assuming fixed coord system. So, for dose[k, i, j], k correspond to y,
    # i corresponds to -z and j corresponds to x

    if idx is None:
        idx = np.unravel_index(np.argmax(dose), dose.shape)

    xp, yp, zp = _get_point_at_idx(idx, axes)

    # Transverse
    heatmap_tra = _generate_heatmap(axes, dose, idx, anatomical_plane="transverse")
    fig.add_trace(
        heatmap_tra,
        row=1,
        col=1,
    )
    fig.add_hline(y=zp, line_color="Silver", row=1, col=1)
    fig.add_vline(x=xp, line_color="Silver", row=1, col=1)

    # Sagittal
    heatmap_sag = _generate_heatmap(axes, dose, idx, anatomical_plane="sagittal")
    fig.add_trace(
        heatmap_sag,
        row=1,
        col=2,
    )
    fig.add_hline(y=zp, line_color="Silver", row=1, col=2)
    fig.add_vline(x=yp, line_color="Silver", row=1, col=2)

    # Coronal
    heatmap_cor = _generate_heatmap(axes, dose, idx, anatomical_plane="coronal")
    fig.add_trace(
        heatmap_cor,
        row=2,
        col=1,
    )
    fig.add_hline(y=yp, line_color="Silver", row=2, col=1)
    fig.add_vline(x=xp, line_color="Silver", row=2, col=1)


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

    fig["layout"].update(margin=dict(l=5, r=5, b=5, t=30, pad=0))

    return fig
