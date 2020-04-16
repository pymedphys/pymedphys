# pylint: disable = pointless-statement, pointless-string-statement, no-value-for-parameter, expression-not-assigned


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

site_options = list(SITE_DIRECTORIES.keys())

DEFAULT_ICOM_DIRECTORY = r"\\rccc-physicssvr\iComLogFiles\patients"
DEFAULT_PNG_OUTPUT_DIRECTORY = r"\\pdc\PExIT\Physics\Patient Specific Logfile Fluence"

GRID = pymedphys.mudensity.grid()
COORDS = (GRID["jaw"], GRID["mlc"])

DEFAULT_GAMMA_OPTIONS = {
    "dose_percent_threshold": 2,
    "distance_mm_threshold": 0.5,
    "local_gamma": True,
    "quiet": True,
    "max_gamma": 5,
}

st.sidebar.markdown(
    """
    ## Advanced Options

    Enable advanced functionality by ticking the below.
    """
)
advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")

if advanced_mode:

    st.sidebar.markdown(
        """
        ### Gamma parameters
        """
    )
    gamma_options = {
        **DEFAULT_GAMMA_OPTIONS,
        **{
            "dose_percent_threshold": st.sidebar.number_input(
                "MU Percent Threshold", DEFAULT_GAMMA_OPTIONS["dose_percent_threshold"]
            ),
            "distance_mm_threshold": st.sidebar.number_input(
                "Distance (mm) Threshold",
                DEFAULT_GAMMA_OPTIONS["distance_mm_threshold"],
            ),
            "local_gamma": st.sidebar.checkbox(
                "Local Gamma", DEFAULT_GAMMA_OPTIONS["local_gamma"]
            ),
            "max_gamma": st.sidebar.number_input(
                "Max Gamma", DEFAULT_GAMMA_OPTIONS["max_gamma"]
            ),
        },
    }
else:
    gamma_options = DEFAULT_GAMMA_OPTIONS


"""
## Selection of data to compare
"""


@st.cache
def delivery_from_icom(icom_stream):
    return pymedphys.Delivery.from_icom(icom_stream)


@st.cache
def delivery_from_tel(tel_path):
    return pymedphys.Delivery.from_monaco(tel_path)


@st.cache
def cached_deliveries_loading(inputs, method_function):
    deliveries = []

    for an_input in inputs:
        deliveries += [method_function(an_input)]

    return deliveries


@st.cache
def load_icom_stream(icom_path):
    with lzma.open(icom_path, "r") as f:
        contents = f.read()

    return contents


@st.cache
def load_icom_streams(icom_paths):
    icom_streams = []

    for icom_path in icom_paths:
        icom_streams += [load_icom_stream(icom_path)]

    return icom_streams


def monaco_input_method(patient_id="", key_namespace="", **_):
    monaco_site = st.radio(
        "Monaco Plan Location", site_options, key=f"{key_namespace}_monaco_site"
    )
    monaco_directory = SITE_DIRECTORIES[monaco_site]["monaco"]

    if advanced_mode:
        monaco_directory

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    ).zfill(6)
    if advanced_mode:
        patient_id

    all_tel_paths = list(monaco_directory.glob(f"*~{patient_id}/plan/*/*tel.1"))
    all_tel_paths = sorted(all_tel_paths, key=os.path.getmtime)

    plan_names_to_choose_from = [
        f"{path.parent.name}/{path.name}" for path in all_tel_paths
    ]

    selected_monaco_plans = st.multiselect(
        "Select Monaco plan(s)",
        plan_names_to_choose_from,
        key=f"{key_namespace}_monaco_plans",
    )

    tel_paths = []

    for plan in selected_monaco_plans:
        current_plans = list(monaco_directory.glob(f"*~{patient_id}/plan/{plan}"))
        assert len(current_plans) == 1
        tel_paths += current_plans

    if advanced_mode:
        [str(path) for path in tel_paths]

    deliveries = cached_deliveries_loading(tel_paths, delivery_from_tel)

    if tel_paths:
        plan_names = ", ".join([path.parent.name for path in tel_paths])
        identifier = f"Monaco ({plan_names})"
    else:
        identifier = None

    results = {
        "patient_id": patient_id,
        "selected_monaco_plans": selected_monaco_plans,
        "data_paths": tel_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results


def dicom_input_method():
    pass


def icom_input_method(
    patient_id="", icom_directory=DEFAULT_ICOM_DIRECTORY, key_namespace="", **_
):
    if advanced_mode:
        icom_directory = st.text_input(
            "iCOM Patient Directory",
            str(icom_directory),
            key=f"{key_namespace}_icom_directory",
        )

    icom_directory = pathlib.Path(icom_directory)

    if advanced_mode:
        patient_id = st.text_input(
            "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
        ).zfill(6)
        patient_id

    icom_deliveries = list(icom_directory.glob(f"{patient_id}_*/*.xz"))
    icom_deliveries = sorted(icom_deliveries)

    icom_files_to_choose_from = [path.stem for path in icom_deliveries]

    timestamps = list(
        pd.to_datetime(icom_files_to_choose_from, format="%Y%m%d_%H%M%S").astype(str)
    )

    selected_icom_deliveries = st.multiselect(
        "Select iCOM delivery timestamp(s)",
        timestamps,
        key=f"{key_namespace}_icom_deliveries",
    )

    icom_filenames = [
        path.replace(" ", "_").replace("-", "").replace(":", "")
        for path in selected_icom_deliveries
    ]

    icom_paths = []
    for icom_filename in icom_filenames:
        icom_paths += list(icom_directory.glob(f"{patient_id}_*/{icom_filename}.xz"))

    if advanced_mode:
        [str(path) for path in icom_paths]

    icom_streams = load_icom_streams(icom_paths)
    deliveries = cached_deliveries_loading(icom_streams, delivery_from_icom)

    if selected_icom_deliveries:
        identifier = f"iCOM ({', '.join(icom_filenames)})"
    else:
        identifier = None

    results = {
        "patient_id": patient_id,
        "icom_directory": str(icom_directory),
        "selected_icom_deliveries": selected_icom_deliveries,
        "data_paths": icom_paths,
        "identifier": identifier,
        "deliveries": deliveries,
    }

    return results


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

DEFAULT_REFERENCE = "Monaco tel.1 filepath"
DEFAULT_EVALUATION = "iCOM stream timestamp"

"""
### Reference
"""

if advanced_mode:
    reference_data_method = st.selectbox(
        "Data Input Method",
        data_method_options,
        index=data_method_options.index(DEFAULT_REFERENCE),
    )

else:
    reference_data_method = DEFAULT_REFERENCE

reference_results = data_method_map[reference_data_method](  # type: ignore
    key_namespace="reference"
)

"""
### Evaluation
"""

if advanced_mode:
    evaluation_data_method = st.selectbox(
        "Data Input Method",
        data_method_options,
        index=data_method_options.index(DEFAULT_EVALUATION),
    )
else:
    evaluation_data_method = DEFAULT_EVALUATION

evaluation_results = data_method_map[evaluation_data_method](  # type: ignore
    key_namespace="evaluation", **reference_results
)


"""
## Output Locations
"""

"""
### eSCAN Directory

The location to save the produced pdf report.
"""

escan_site = st.radio("eScan Site", site_options)
escan_directory = SITE_DIRECTORIES[escan_site]["escan"]

if advanced_mode:
    escan_directory

if advanced_mode:
    """
    ### Image record

    Path to save the image of the results for posterity
    """

    png_output_directory = pathlib.Path(
        st.text_input("png output directory", DEFAULT_PNG_OUTPUT_DIRECTORY)
    )
    png_output_directory

else:
    png_output_directory = pathlib.Path(DEFAULT_PNG_OUTPUT_DIRECTORY)


@st.cache
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
    reference_mudensity,
    evaluation_mudensity,
    gamma,
    gamma_options,
    header_text="",
    footer_text="",
):
    diff = evaluation_mudensity - reference_mudensity
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

    ax_header = fig.add_subplot(gs[0, :])
    ax_hist = fig.add_subplot(gs[1, :])
    ax_footer = fig.add_subplot(gs[4, :])

    ax_header.axis("off")
    ax_footer.axis("off")

    ax_header.text(0, 0, header_text, ha="left", wrap=True, fontsize=30)
    ax_footer.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

    plt.sca(axs[2, 0])
    pymedphys.mudensity.display(GRID, reference_mudensity)
    axs[2, 0].set_title("Reference MU Density")

    plt.sca(axs[2, 1])
    pymedphys.mudensity.display(GRID, evaluation_mudensity)
    axs[2, 1].set_title("Evaluation MU Density")

    plt.sca(axs[3, 0])
    pymedphys.mudensity.display(
        GRID, diff, cmap="seismic", vmin=-largest_item, vmax=largest_item
    )
    plt.title("Evaluation - Reference")

    plt.sca(axs[3, 1])
    pymedphys.mudensity.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
    plt.title(
        "Local Gamma | "
        f"{gamma_options['dose_percent_threshold']}%/"
        f"{gamma_options['distance_mm_threshold']}mm"
    )

    plt.sca(ax_hist)
    plot_gamma_hist(
        gamma,
        gamma_options["dose_percent_threshold"],
        gamma_options["distance_mm_threshold"],
    )

    return fig


@st.cache
def calculate_batch_mudensity(deliveries):
    mudensity = deliveries[0].mudensity()

    for delivery in deliveries[1::]:
        mudensity = mudensity + delivery.mudensity()

    return mudensity


@st.cache
def calculate_gamma(reference_mudensity, evaluation_mudensity, gamma_options):
    gamma = pymedphys.gamma(
        COORDS,
        to_tuple(reference_mudensity),
        COORDS,
        to_tuple(evaluation_mudensity),
        **gamma_options,
    )

    return gamma


def run_calculation(
    reference_results,
    evaluation_results,
    gamma_options,
    escan_directory,
    png_output_directory,
):
    st.write("Calculating Reference MU Density...")
    reference_mudensity = calculate_batch_mudensity(reference_results["deliveries"])

    st.write("Calculating Evaluation MU Density...")
    evaluation_mudensity = calculate_batch_mudensity(evaluation_results["deliveries"])

    st.write("Calculating Gamma...")
    gamma = calculate_gamma(reference_mudensity, evaluation_mudensity, gamma_options)

    patient_id = reference_results["patient_id"]

    st.write("Creating figure...")
    output_base_filename = (
        f"{patient_id} {reference_results['identifier']} vs "
        f"{evaluation_results['identifier']}"
    )
    pdf_filepath = str(
        escan_directory.joinpath(f"{output_base_filename}.pdf").resolve()
    )
    png_filepath = str(
        png_output_directory.joinpath(f"{output_base_filename}.png").resolve()
    )

    header_text = (
        f"Patient ID: {patient_id}\n"
        f"Reference: {reference_results['identifier']}\n"
        f"Evaluation: {evaluation_results['identifier']}\n"
    )

    reference_path_strings = "\n    ".join(
        [str(path) for path in reference_results["data_paths"]]
    )
    evaluation_path_strings = "\n    ".join(
        [str(path) for path in evaluation_results["data_paths"]]
    )

    footer_text = (
        f"reference path(s): {reference_path_strings}\n"
        f"evaluation path(s): {evaluation_path_strings}\n"
        f"png record: {png_filepath}"
    )

    fig = plot_and_save_results(
        reference_mudensity,
        evaluation_mudensity,
        gamma,
        gamma_options,
        header_text=header_text,
        footer_text=footer_text,
    )

    fig.tight_layout()

    st.write("Saving figure...")
    plt.savefig(png_filepath, dpi=300)
    os.system(f'magick convert "{png_filepath}" "{pdf_filepath}"')

    st.write("## Results")
    st.pyplot()


"""
## Calculation
"""

if st.button("Run Calculation"):
    run_calculation(
        reference_results,
        evaluation_results,
        gamma_options,
        escan_directory,
        png_output_directory,
    )
