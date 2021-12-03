# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import base64
import functools
import os
import pathlib
import subprocess
import sys
from datetime import datetime

from pymedphys._imports import imageio
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st
from pymedphys._imports import streamlit_ace, timeago, tomlkit

import pymedphys
from pymedphys._streamlit.utilities import exceptions as _exceptions
from pymedphys._streamlit.utilities import misc as st_misc

from . import _config, _dicom, _icom, _monaco, _mosaiq, _trf

DATA_OPTION_LABELS = {
    "monaco": "Monaco tel.1 filepath",
    "dicom": "DICOM RTPlan file upload",
    "icom": "iCOM record timestamp",
    "trf": "Linac Backup `.trf` filepath",
    "mosaiq": "Mosaiq SQL query",
}

LEAF_PAIR_WIDTHS = (10,) + (5,) * 78 + (10,)
MAX_LEAF_GAP = 410
GRID_RESOLUTION = 1
GRID = pymedphys.metersetmap.grid(
    max_leaf_gap=MAX_LEAF_GAP,
    grid_resolution=GRID_RESOLUTION,
    leaf_pair_widths=LEAF_PAIR_WIDTHS,
)
COORDS = (GRID["jaw"], GRID["mlc"])


def sidebar_overview():
    overview_placeholder = st.sidebar.empty()

    def set_overview_data(patient_id, patient_name, total_mu):
        overview_placeholder.markdown(
            f"Patient ID: `{patient_id}`\n\n"
            f"Patient Name: `{patient_name}`\n\n"
            f"Total MU: `{total_mu}`"
        )

    return set_overview_data


def get_most_recent_file_and_print(linac_id, filepaths):
    if not isinstance(filepaths, list):
        raise ValueError("Filepaths needs to be a list")

    try:
        latest_filepath = max(filepaths, key=os.path.getmtime)
    except ValueError:
        st.sidebar.markdown(f"{linac_id}: `Never`")
        return

    most_recent = datetime.fromtimestamp(os.path.getmtime(latest_filepath))
    now = datetime.now()

    if most_recent > now:
        most_recent = now

    human_readable = timeago.format(most_recent, now)

    st.sidebar.markdown(f"{linac_id}: `{human_readable}`")


def icom_status(linac_id, icom_directory):
    filepaths = list(pathlib.Path(icom_directory).glob("*.txt"))
    get_most_recent_file_and_print(linac_id, filepaths)


def trf_status(linac_id, backup_directory):
    directory = pathlib.Path(backup_directory).joinpath(linac_id)
    filepaths = list(directory.glob("*.zip"))
    get_most_recent_file_and_print(linac_id, filepaths)


def show_status_indicators(config):
    if st.sidebar.button("Check status of iCOM and backups"):
        try:
            linac_icom_live_stream_directories = (
                _config.get_icom_live_stream_directories(config)
            )
            linac_indexed_backups_directory = _config.get_indexed_backups_directory(
                config
            )
        except KeyError:
            st.sidebar.write(
                _exceptions.ConfigMissing(
                    "iCOM and/or TRF backup configuration is missing. "
                    "Unable to show status."
                )
            )

            return

        linac_ids = list(linac_icom_live_stream_directories.keys())

        st.sidebar.markdown(
            """
            ## Last recorded iCOM stream
            """
        )

        for linac_id, icom_directory in linac_icom_live_stream_directories.items():
            icom_status(linac_id, icom_directory)

        st.sidebar.markdown(
            """
            ## Last indexed backup
            """
        )

        for linac_id in linac_ids:
            trf_status(linac_id, linac_indexed_backups_directory)


def display_deliveries(deliveries):
    if not deliveries:
        return 0

    st.write(
        """
        #### Overview of selected deliveries
        """
    )

    data = []
    for delivery in deliveries:
        num_control_points = len(delivery.mu)

        if num_control_points != 0:
            total_mu = delivery.mu[-1]
        else:
            total_mu = 0

        data.append([total_mu, num_control_points])

    columns = ["MU", "Number of Data Points"]
    df = pd.DataFrame(data=data, columns=columns)
    st.write(df)

    total_mu = round(df["MU"].sum(), 1)

    st.write(f"Total MU: `{total_mu}`")

    return total_mu


def get_input_data_ui(
    overview_updater_map,
    data_method_map,
    default_method,
    key_namespace,
    advanced_mode,
    **previous_results,
):
    if advanced_mode:
        data_method_options = list(data_method_map.keys())
        data_method = st.selectbox(
            "Data Input Method",
            data_method_options,
            index=data_method_options.index(default_method),
        )

    else:
        data_method = default_method

    results = data_method_map[data_method](  # type: ignore
        key_namespace=key_namespace,
        advanced_mode=advanced_mode,
        **previous_results,
    )

    try:
        total_mu = round(display_deliveries(results["deliveries"]), 1)
    except KeyError:
        total_mu = 0

    try:
        patient_id = results["patient_id"]
    except KeyError:
        patient_id = ""

    try:
        patient_name = results["patient_name"]
    except KeyError:
        patient_name = ""

    overview_updater_map[key_namespace](patient_id, patient_name, total_mu)

    return results


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
    reference_metersetmap,
    evaluation_metersetmap,
    gamma,
    gamma_options,
    png_record_directory,
    header_text="",
    footer_text="",
):
    reference_filepath = png_record_directory.joinpath("reference.png")
    evaluation_filepath = png_record_directory.joinpath("evaluation.png")
    diff_filepath = png_record_directory.joinpath("diff.png")
    gamma_filepath = png_record_directory.joinpath("gamma.png")

    diff = evaluation_metersetmap - reference_metersetmap

    imageio.imwrite(reference_filepath, reference_metersetmap)
    imageio.imwrite(evaluation_filepath, evaluation_metersetmap)
    imageio.imwrite(diff_filepath, diff)
    imageio.imwrite(gamma_filepath, gamma)

    largest_metersetmap = np.max(
        [np.max(evaluation_metersetmap), np.max(reference_metersetmap)]
    )
    largest_diff = np.max(np.abs(diff))

    widths = [1, 1]
    heights = [0.5, 1, 1, 1, 0.4]
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

    ax_header.text(0, 0, header_text, ha="left", wrap=True, fontsize=21)
    ax_footer.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

    plt.sca(axs[2, 0])
    pymedphys.metersetmap.display(
        GRID, reference_metersetmap, vmin=0, vmax=largest_metersetmap
    )
    axs[2, 0].set_title("Reference MetersetMap")

    plt.sca(axs[2, 1])
    pymedphys.metersetmap.display(
        GRID, evaluation_metersetmap, vmin=0, vmax=largest_metersetmap
    )
    axs[2, 1].set_title("Evaluation MetersetMap")

    plt.sca(axs[3, 0])
    pymedphys.metersetmap.display(
        GRID, diff, cmap="seismic", vmin=-largest_diff, vmax=largest_diff
    )
    plt.title("Evaluation - Reference")

    plt.sca(axs[3, 1])
    pymedphys.metersetmap.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
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


@st.cache(hash_funcs={pymedphys.Delivery: hash})
def calculate_metersetmap(delivery):
    return delivery.metersetmap(
        max_leaf_gap=MAX_LEAF_GAP,
        grid_resolution=GRID_RESOLUTION,
        leaf_pair_widths=LEAF_PAIR_WIDTHS,
    )


def calculate_batch_metersetmap(deliveries):
    metersetmap = calculate_metersetmap(deliveries[0])

    for delivery in deliveries[1::]:
        metersetmap = metersetmap + calculate_metersetmap(delivery)

    return metersetmap


@st.cache
def calculate_gamma(reference_metersetmap, evaluation_metersetmap, gamma_options):
    gamma = pymedphys.gamma(
        COORDS,
        to_tuple(reference_metersetmap),
        COORDS,
        to_tuple(evaluation_metersetmap),
        **gamma_options,
    )

    return gamma


def advanced_debugging(config):
    st.sidebar.markdown("# Advanced Debugging")
    if st.sidebar.button("Compare Baseline to Output Directory"):
        st.write(
            """
            ## Comparing Results to Baseline
            """
        )

        baseline_directory = pathlib.Path(
            config["debug"]["baseline_directory"]
        ).resolve()

        png_baseline_directory = baseline_directory.joinpath("png")

        baseline_png_paths = [
            path for path in (png_baseline_directory.rglob("*")) if path.is_file()
        ]

        relative_png_paths = [
            path.relative_to(png_baseline_directory) for path in baseline_png_paths
        ]

        output_dir = pathlib.Path(config["output"]["png_directory"]).resolve()

        evaluation_png_paths = [
            output_dir.joinpath(path) for path in relative_png_paths
        ]

        for baseline, evaluation in zip(baseline_png_paths, evaluation_png_paths):

            st.write(f"### {baseline.parent.name}/{baseline.name}")

            st.write(f"`{baseline}`\n\n**vs**\n\n`{evaluation}`")

            baseline_image = imageio.imread(baseline)

            try:
                evaluation_image = imageio.imread(evaluation)
            except FileNotFoundError as e:
                st.write(
                    """
                    #### File was not found
                    """
                )

                st.write(e)

                st.write(
                    f"""
                    For debugging purposes, here are all the files that
                    were found within {str(output_dir)}
                    """
                )

                st.write(
                    [str(path) for path in output_dir.rglob("*") if path.is_file()]
                )

                return

            agree = np.allclose(baseline_image, evaluation_image)
            st.write(f"Images Agree: `{agree}`")


def run_calculation(
    reference_results,
    evaluation_results,
    gamma_options,
    escan_directory: pathlib.Path,
    png_output_directory: pathlib.Path,
):
    st.write("Calculating Reference MetersetMap...")
    reference_metersetmap = calculate_batch_metersetmap(reference_results["deliveries"])

    st.write("Calculating Evaluation MetersetMap...")
    evaluation_metersetmap = calculate_batch_metersetmap(
        evaluation_results["deliveries"]
    )

    st.write("Calculating Gamma...")
    gamma = calculate_gamma(
        reference_metersetmap, evaluation_metersetmap, gamma_options
    )

    patient_id = reference_results["patient_id"]

    st.write("Creating figure...")
    output_base_filename = (
        f"{patient_id} {reference_results['identifier']} vs "
        f"{evaluation_results['identifier']}"
    )
    pdf_filepath = str(
        escan_directory.joinpath(f"{output_base_filename}.pdf").resolve()
    )
    png_record_directory = png_output_directory.joinpath(output_base_filename)
    png_record_directory.mkdir(exist_ok=True, parents=True)
    png_filepath = str(png_record_directory.joinpath("report.png").resolve())

    try:
        patient_name_text = f"Patient Name: {reference_results['patient_name']}\n"
    except KeyError:
        patient_name_text = ""

    header_text = (
        f"Patient ID: {patient_id}\n"
        f"{patient_name_text}"
        f"Reference: {reference_results['identifier']}\n"
        f"Evaluation: {evaluation_results['identifier']}\n"
    )

    reference_path_strings = "\n    ".join(
        [str(path.resolve()) for path in reference_results["data_paths"]]
    )
    evaluation_path_strings = "\n    ".join(
        [str(path.resolve()) for path in evaluation_results["data_paths"]]
    )

    footer_text = (
        f"reference path(s): {reference_path_strings}\n"
        f"evaluation path(s): {evaluation_path_strings}\n"
        f"png record: {png_filepath}"
    )

    fig = plot_and_save_results(
        reference_metersetmap,
        evaluation_metersetmap,
        gamma,
        gamma_options,
        png_record_directory,
        header_text=header_text,
        footer_text=footer_text,
    )

    fig.tight_layout()

    st.write("## Results")
    st.pyplot(fig)

    st.write("## Saving reports")
    st.write("### PNG")
    st.write("Saving figure as PNG...")
    plt.savefig(png_filepath, dpi=100)
    st.write(f"Saved:\n\n`{png_filepath}`")
    convert_png_to_pdf(png_filepath, pdf_filepath)


def convert_png_to_pdf(png_filepath, pdf_filepath):
    st.write("### PDF")
    st.write("Converting PNG to PDF...")

    try:
        subprocess.check_call(
            f'magick convert "{png_filepath}" "{pdf_filepath}"', shell=True
        )
        success = True
    except subprocess.CalledProcessError:
        try:
            subprocess.check_call(
                f'convert "{png_filepath}" "{pdf_filepath}"', shell=True
            )
            success = True
        except subprocess.CalledProcessError:
            success = False

    if success:
        st.write(f"Created:\n\n`{pdf_filepath}`")

        with open(pdf_filepath, "rb") as f:
            pdf_contents = f.read()

        pdf_filename = pathlib.Path(pdf_filepath).name

        pdf_b64 = base64.b64encode(pdf_contents).decode()
        href = f"""
            <a href="data:file/zip;base64,{pdf_b64}" download='{pdf_filename}'>
                Click to download {pdf_filename}
            </a>
        """
        st.markdown(href, unsafe_allow_html=True)

    else:
        if sys.platform == "win32":
            url_hash_parameter = "#windows"
        else:
            url_hash_parameter = ""

        download_url = (
            f"https://imagemagick.org/script/download.php{url_hash_parameter}"
        )

        st.write(
            _exceptions.UnableToCreatePDF(
                "Please install Image Magick to create PDF reports "
                f"<{download_url}>."
            )
        )


def main():
    st.write(
        """
        Tool to compare the MetersetMap between planned and delivery.
        """
    )

    st.sidebar.markdown(
        """
        # Configuration Choice
        """
    )

    config_options = list(_config.CONFIG_OPTIONS.keys())

    try:
        _config.get_config(config_options[0])
    except FileNotFoundError:
        config_options.pop(0)

    config_mode = st.sidebar.radio("Config Mode", options=config_options)
    config = _config.get_config(config_mode)

    show_config = st.sidebar.checkbox("Show/edit config", False)
    if show_config:
        st.write("## Configuration")
        config = tomlkit.loads(
            streamlit_ace.st_ace(value=tomlkit.dumps(config), language="toml")
        )

    st.sidebar.markdown(
        """
        # MetersetMap Overview
        """
    )

    st.sidebar.markdown(
        """
        ## Reference
        """
    )

    set_reference_overview = sidebar_overview()

    st.sidebar.markdown(
        """
        ## Evaluation
        """
    )

    set_evaluation_overview = sidebar_overview()

    overview_updater_map = {
        "reference": set_reference_overview,
        "evaluation": set_evaluation_overview,
    }

    st.sidebar.markdown(
        """
        # Status indicators
        """
    )

    show_status_indicators(config)

    st.sidebar.markdown(
        """
        # Advanced options

        Enable advanced functionality by ticking the below.
        """
    )
    advanced_mode = st.sidebar.checkbox("Run in Advanced Mode")

    gamma_options = _config.get_gamma_options(config, advanced_mode)

    data_option_functions = {
        "monaco": _monaco.monaco_input_method,
        "dicom": _dicom.dicom_input_method,
        "icom": _icom.icom_input_method,
        "trf": _trf.trf_input_method,
        "mosaiq": _mosaiq.mosaiq_input_method,
    }

    default_reference_id = config["data_methods"]["default_reference"]
    default_evaluation_id = config["data_methods"]["default_evaluation"]
    available_data_methods = config["data_methods"]["available"]

    default_reference = DATA_OPTION_LABELS[default_reference_id]
    default_evaluation = DATA_OPTION_LABELS[default_evaluation_id]

    data_method_map = {}
    for method in available_data_methods:
        data_method_map[DATA_OPTION_LABELS[method]] = functools.partial(
            data_option_functions[method], config=config
        )

    st.write(
        """
        ## Selection of data to compare
        """
    )

    st.write("---")

    ref_col, eval_col = st.beta_columns(2)

    with ref_col:
        st.write(
            """
            ### Reference
            """
        )

        reference_results = get_input_data_ui(
            overview_updater_map,
            data_method_map,
            default_reference,
            "reference",
            advanced_mode,
        )

    with eval_col:
        st.write(
            """
            ### Evaluation
            """
        )

        evaluation_results = get_input_data_ui(
            overview_updater_map,
            data_method_map,
            default_evaluation,
            "evaluation",
            advanced_mode,
            **reference_results,
        )

    st.write("---")

    st.write(
        """
        ## Output Locations
        """
    )

    st.write(
        """
        ### eSCAN Directory

        The location to save the produced pdf report.
        """
    )

    default_site = evaluation_results.get("site", None)
    if default_site is None:
        default_site = reference_results.get("site", None)

    _, escan_directory = st_misc.get_site_and_directory(
        config,
        "eScan Site",
        "escan",
        default=default_site,
        key="escan_export_site_picker",
    )

    escan_directory = pathlib.Path(os.path.expanduser(escan_directory)).resolve()

    if advanced_mode:
        st.write(escan_directory)

    default_png_output_directory = config["output"]["png_directory"]

    if advanced_mode:
        st.write(
            """
            ### Image record

            Path to save the image of the results for posterity
            """
        )

        png_output_directory = pathlib.Path(
            st.text_input("png output directory", default_png_output_directory)
        )
        st.write(png_output_directory.resolve())

    else:
        png_output_directory = pathlib.Path(default_png_output_directory)

    png_output_directory = pathlib.Path(
        os.path.expanduser(png_output_directory)
    ).resolve()

    st.write(
        """
        ## Calculation
        """
    )

    if st.button("Run Calculation"):

        st.write(
            """
            ### MetersetMap usage warning
            """
        )

        st.warning(pymedphys.metersetmap.WARNING_MESSAGE)

        st.write(
            """
            ### Calculation status
            """
        )

        run_calculation(
            reference_results,
            evaluation_results,
            gamma_options,
            escan_directory,
            png_output_directory,
        )

    if advanced_mode:
        advanced_debugging(config)
