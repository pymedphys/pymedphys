# pylint: disable = pointless-statement, pointless-string-statement, no-value-for-parameter


import lzma
import os
import pathlib
import time

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

import pymedphys
import streamlit as st


"""
# MU Density comparison tool

Tool to compare the MU Density between planned and delivery.
"""

"""
## Selection of data to compare
"""


def monaco_input_method():
    pass


def dicom_input_method():
    pass


def icom_input_method():
    pass


def trf_input_method():
    pass


def mosaiq_input_method():
    pass


data_method_map = {
    "Monaco tel.1 filepath": monaco_input_method,
    "DICOM RTPlan file upload": dicom_input_method,
    "iCOM stream timestamp": icom_input_method,
    "Linac Backup `.trf` filepath": trf_input_method,
    "Mosaiq SQL query": mosaiq_input_method,
}

data_method_options = list(data_method_map.keys())

"""
### Reference
"""

reference_data_method = st.selectbox("Data Input Method", data_method_options, index=0)
reference_delivery = data_method_map[reference_data_method]()

"""
### Evaluation
"""

evaluation_data_method = st.selectbox("Data Input Method", data_method_options, index=2)
evaluation_delivery = data_method_map[evaluation_data_method]()


SITE_DIRECTORIES = {
    "rccc": {
        "monaco": pathlib.Path(r"\\monacoda\FocalData\RCCC\1~Clinical"),
        "escan": pathlib.Path(
            r"\\pdc\Shared\Scanned Documents\RT\PhysChecks\Logfile PDFs"
        ),
    },
    "nbcc": {
        "monaco": pathlib.Path(r"\\tunnel-nbcc-monaco\FOCALDATA\NBCCC\1~Clinical"),
        "escan": pathlib.Path(r"\\tunnel-nbcc-pdc\Shared\SCAN\ESCAN\Phys\Logfile PDFs"),
    },
    "sash": {
        "monaco": pathlib.Path(
            r"\\tunnel-sash-monaco\Users\Public\Documents\CMS\FocalData\SASH\1~Clinical"
        ),
        "escan": pathlib.Path(
            r"\\tunnel-sash-physics-server\SASH-Mosaiq-eScan\Logfile PDFs"
        ),
    },
}

icom_directory = pathlib.Path(r"\\rccc-physicssvr\iComLogFiles\patients")
output_directory = pathlib.Path(r"\\pdc\PExIT\Physics\Patient Specific Logfile Fluence")

GRID = pymedphys.mudensity.grid()
COORDS = (GRID["jaw"], GRID["mlc"])

GAMMA_OPTIONS = {
    "dose_percent_threshold": 2,  # Not actually comparing dose though
    "distance_mm_threshold": 0.5,
    "local_gamma": True,
    "quiet": True,
    "max_gamma": 5,
}

"""
## Input / Output Directory Selections
"""

site_options = list(SITE_DIRECTORIES.keys())

monaco_site = st.radio("Monaco Site", site_options)
monaco_directory = SITE_DIRECTORIES[monaco_site]["monaco"]
monaco_directory

escan_site = st.radio("eScan Site", site_options)
escan_directory = SITE_DIRECTORIES[escan_site]["escan"]
escan_directory

patient_id = st.text_input("Patient ID").zfill(6)
patient_id


all_tel_paths = list(monaco_directory.glob(f"*~{patient_id}/plan/*/*tel.1"))
all_tel_paths = sorted(all_tel_paths, key=os.path.getmtime)

plan_names_to_choose_from = [
    f"{path.parent.name}/{path.name}" for path in all_tel_paths
]

icom_deliveries = list(icom_directory.glob(f"{patient_id}_*/*.xz"))
icom_deliveries = sorted(icom_deliveries)

icom_files_to_choose_from = [path.stem for path in icom_deliveries]

timestamps = list(
    pd.to_datetime(icom_files_to_choose_from, format="%Y%m%d_%H%M%S").astype(str)
)

delivery_timestamp = timestamps
plan_names = plan_names_to_choose_from


selected_monaco_plans = ["LSPINE/tel.1"]
selected_icom_deliveries = ["2020-04-15 15:56:15"]


def to_tuple(array):
    return tuple(map(tuple, array))


def plot_gamma_hist(gamma, percent, dist):
    valid_gamma = gamma[~np.isnan(gamma)]

    plt.hist(valid_gamma, 50, density=True)
    pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

    plt.title(
        "Local Gamma ({0}%/{1}mm) | Percent Pass: {2:.2f} % | Mean Gamma: {3:.2f} | Max Gamma: {4:.2f}".format(
            percent, dist, pass_ratio * 100, np.mean(valid_gamma), np.max(valid_gamma)
        )
    )


def plot_and_save_results(
    mudensity_tel, mudensity_icom, gamma, header_text="", footer_text=""
):
    diff = mudensity_icom - mudensity_tel
    largest_item = np.max(np.abs(diff))

    widths = [1, 1]
    heights = [0.3, 1, 1, 1, 0.1]
    gs_kw = dict(width_ratios=widths, height_ratios=heights)

    fig, axs = plt.subplots(5, 2, figsize=(10, 16), gridspec_kw=gs_kw)
    gs = axs[0, 0].get_gridspec()

    for ax in axs[0, 0:]:
        ax.remove()

    for ax in axs[1, 0:]:
        ax.remove()

    for ax in axs[4, 0:]:
        ax.remove()

    axheader = fig.add_subplot(gs[0, :])
    axhist = fig.add_subplot(gs[1, :])
    axfooter = fig.add_subplot(gs[4, :])

    axheader.axis("off")
    axfooter.axis("off")

    axheader.text(0, 0, header_text, ha="left", wrap=True, fontsize=30)
    axfooter.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

    plt.sca(axs[2, 0])
    pymedphys.mudensity.display(GRID, mudensity_tel)
    axs[2, 0].set_title("Monaco Plan MU Density")

    plt.sca(axs[2, 1])
    pymedphys.mudensity.display(GRID, mudensity_icom)
    axs[2, 1].set_title("Recorded iCOM MU Density")

    plt.sca(axs[3, 0])
    pymedphys.mudensity.display(
        GRID, diff, cmap="seismic", vmin=-largest_item, vmax=largest_item
    )
    plt.title("iCOM - Monaco")

    plt.sca(axs[3, 1])
    pymedphys.mudensity.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
    plt.title(
        "Local Gamma | "
        f"{GAMMA_OPTIONS['dose_percent_threshold']}%/"
        f"{GAMMA_OPTIONS['distance_mm_threshold']}mm"
    )

    plt.sca(axhist)
    plot_gamma_hist(
        gamma,
        GAMMA_OPTIONS["dose_percent_threshold"],
        GAMMA_OPTIONS["distance_mm_threshold"],
    )

    return fig


@st.cache
def deliveries_from_icom(icom_streams):
    deliveries_icom = []

    for icom_stream in icom_streams:
        deliveries_icom += [pymedphys.Delivery.from_icom(icom_stream)]

    return deliveries_icom


@st.cache
def deliveries_from_tel(tel_paths):
    deliveries_tel = []

    for tel_path in tel_paths:
        deliveries_tel += [pymedphys.Delivery.from_monaco(tel_path)]

    return deliveries_tel


@st.cache
def calculate_batch_mudensity(deliveries):
    mudensity = deliveries[0].mudensity()

    for delivery in deliveries[1::]:
        mudensity = mudensity + delivery.mudensity()

    return mudensity


def run_calculation(
    patient_id,
    selected_monaco_plans,
    selected_icom_deliveries,
    monaco_directory,
    escan_directory,
):
    st.write("## Output")

    tel_paths = []

    for plan in selected_monaco_plans:
        current_plans = list(monaco_directory.glob(f"*~{patient_id}/plan/{plan}"))
        assert len(current_plans) == 1
        tel_paths += current_plans

    st.write("### Monaco plan paths", [str(path) for path in tel_paths])

    icom_paths = []

    for icom_delivery in selected_icom_deliveries:
        icom_filename = (
            icom_delivery.replace(" ", "_").replace("-", "").replace(":", "")
        )
        icom_paths += list(icom_directory.glob(f"{patient_id}_*/{icom_filename}.xz"))

    st.write("### iCOM log file paths", [str(path) for path in icom_paths])

    icom_streams = []

    for icom_path in icom_paths:
        with lzma.open(icom_path, "r") as f:
            icom_streams += [f.read()]

    st.write("### Loading Data")
    deliveries_tel = deliveries_from_tel(tel_paths)
    deliveries_icom = deliveries_from_icom(icom_streams)

    st.write("### Beginning calculation")
    st.write("Calculating Monaco MU Density...")
    mudensity_tel = calculate_batch_mudensity(deliveries_tel)

    st.write("Calculating iCOM MU Density...")
    mudensity_icom = calculate_batch_mudensity(deliveries_icom)

    st.write("Calculating Gamma...")
    gamma = pymedphys.gamma(
        COORDS,
        to_tuple(mudensity_tel),
        COORDS,
        to_tuple(mudensity_icom),
        **GAMMA_OPTIONS,
    )

    tel_path = tel_paths[0]

    st.write("Creating figure...")
    results_dir = output_directory.joinpath(
        patient_id, tel_path.parent.name, icom_path.stem
    )
    results_dir.mkdir(exist_ok=True, parents=True)

    header_text = f"Patient ID: {patient_id}\n" f"Plan Name: {tel_path.parent.name}\n"

    icom_path_strings = "\n    ".join([str(icom_path) for icom_path in icom_paths])
    tel_path_strings = "\n    ".join([str(tel_path) for tel_path in tel_paths])

    footer_text = (
        f"tel.1 file path(s): {tel_path_strings}\n"
        f"icom file path(s): {icom_path_strings}\n"
        f"results path: {str(results_dir)}"
    )

    png_filepath = str(results_dir.joinpath("result.png").resolve())
    pdf_filepath = str(
        escan_directory.joinpath(
            f"{patient_id}-{selected_monaco_plans[0].replace('/','-')}.pdf"
        ).resolve()
    )

    fig = plot_and_save_results(
        mudensity_tel,
        mudensity_icom,
        gamma,
        header_text=header_text,
        footer_text=footer_text,
    )

    fig.tight_layout()

    st.write("Saving figure...")
    plt.savefig(png_filepath, dpi=300)
    os.system(f'magick convert "{png_filepath}" "{pdf_filepath}"')

    st.write("## Results")
    st.pyplot()


if st.button("Run Calculation"):
    run_calculation(
        patient_id,
        selected_monaco_plans,
        selected_icom_deliveries,
        monaco_directory,
        escan_directory,
    )
