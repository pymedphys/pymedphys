from typing import BinaryIO, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st
from pymedphys._imports.matplotlib import pyplot as plt

from pymedphys._dicom.coords import xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._dicom.utilities import pretty_patient_name
from pymedphys._streamlit import categories

CATEGORY = categories.PRE_ALPHA
TITLE = "Plot 3D Dose from DICOM - Matplotlib"


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

    axes_fixed = xyz_axes_from_dataset(ds, coord_system="FIXED")
    dose = dose_from_dataset(ds)
    max_dose_idx = _get_idx_of_max_dose(dose)
    max_dose_xp, max_dose_yp, max_dose_zp = _get_point_at_idx(max_dose_idx, axes_fixed)
    max_dose_val = dose[max_dose_idx]

    with right_column:
        st.write(
            f"""

            ## Details

            * Patient ID: `{ds.PatientID}`
            * Patient name: `{pretty_patient_name(ds)}`
            * Max dose position (mm): `({max_dose_xp:.2f}, {max_dose_yp:.2f}, {max_dose_zp:.2f})`)
            * Max dose value (Gy): `{max_dose_val:.4f}`)
            """
        )

    fig, ax = plt.subplots()

    with left_column:

        st.write("---")
        y_slider_pos = st.slider(
            label="y (mm)",
            min_value=float(axes_fixed[1][0]),
            max_value=float(axes_fixed[1][-1]),
            value=float(max_dose_yp),
            step=float(axes_fixed[0][1] - axes_fixed[0][0]),
            format="%f",
            key="y_slice",
        )

        dose_slice = dose[np.where(axes_fixed[1] == y_slider_pos)[0][0], :, :]

        _plot_dose(
            fig,
            ax,
            dose_slice,
            abscissa=axes_fixed[0],
            ordinate=axes_fixed[2],
            norm_val=max_dose_val,
        )


def _load_rtdose_file(fh: BinaryIO):
    try:
        ds = pydicom.dcmread(fh)
    except pydicom.errors.InvalidDicomError as e:
        raise ValueError(f"'{fh.name}' is not a valid DICOM file") from e

    if ds.Modality != "RTDOSE":
        raise ValueError("DICOM dataset is not RT Dose")

    return ds


def _plot_dose(fig, ax, dose_slice, abscissa, ordinate, norm_val):
    # Assuming fixed coord system. So, for dose[k, i, j], k correspond to y,
    # i corresponds to -z and j corresponds to x

    im = ax.imshow(
        dose_slice,
        cmap="jet",
        vmin=0,
        vmax=norm_val,
        aspect="equal",
        extent=(abscissa[0], abscissa[-1], ordinate[-1], ordinate[0]),
    )
    fig.colorbar(im)
    st.pyplot(fig)


def _get_point_at_idx(idx, axes):
    return (
        axes[0][idx[2]],
        axes[1][idx[0]],
        axes[2][idx[1]],
    )


def _get_idx_of_max_dose(dose):
    return np.unravel_index(np.argmax(dose), dose.shape)
