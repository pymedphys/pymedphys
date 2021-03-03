# Copyright (C) 2015,2020-2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

import pymedphys._electronfactors as electronfactors
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc as _misc

# Old code warning, the below is Simon Biggs from 2015... be nice to him

CATEGORY = categories.ALPHA
TITLE = "Electron Insert Factor Modelling"

ELECTRON_MODEL_PATTERN = r"RiverinaAgility - (\d+)MeV"
APPLICATOR_PATTERN = r"(\d+)X\d+"


def main():
    config = _config.get_config()
    clinical_directory = _get_clinical_directory(config)

    patient_id = st.text_input("Patient ID")

    if patient_id == "":
        st.stop()

    tel_filepaths = list(clinical_directory.glob(f"*~{patient_id}/plan/*/*tel.1"))

    for filepath in tel_filepaths:
        _logic_per_telfile(filepath)


def _get_clinical_directory(config):
    site_directories = _config.get_site_directories(config)
    chosen_site = _misc.site_picker(config, "Site")
    clinical_directory = site_directories[chosen_site]["monaco"]

    try:
        if not clinical_directory.exists():
            st.error(f"Unable to access `{clinical_directory}`")
            st.stop()
    except OSError as e:
        st.error(e)
        st.stop()

    return clinical_directory


def _logic_per_telfile(filepath):
    st.write("---")
    st.write("Filepath: `{}`".format(filepath))

    with open(filepath, "r") as file:
        tel_contents = np.array(file.read().splitlines())

    reference_indices = []
    for i, item in enumerate(tel_contents):
        if re.search(ELECTRON_MODEL_PATTERN, item):
            reference_indices.append(i)

    for reference_index in reference_indices:
        _per_reference_index(tel_contents, reference_index)


def _per_reference_index(tel_contents, reference_index):
    applicator = float(
        re.search(APPLICATOR_PATTERN, tel_contents[reference_index + 12]).group(1)
    )
    energy = float(
        re.search(ELECTRON_MODEL_PATTERN, tel_contents[reference_index]).group(1)
    )
    ssd = 100

    st.write(f"Applicator: `{applicator} cm` | Energy: `{energy} MeV`")

    # coords start 51 lines after electron model name
    coords_index_start = reference_index + 51
    insert_initial_range = tel_contents[coords_index_start::]

    # coords stop right before a line containing 0
    insert_stop = np.where(insert_initial_range == "0")[0][0]
    insert_coords_string = insert_initial_range[:insert_stop]

    insert_coords = np.fromstring(",".join(insert_coords_string), sep=",")
    x = insert_coords[0::2] / 10
    y = insert_coords[1::2] / 10

    width, length, circle_centre = electronfactors.parameterise_insert(x, y)

    st.write(f"Width: `{width}`")
    st.write(f"Length: `{length}`")

    fig = _plot_insert(
        x,
        y,
        width,
        length,
        circle_centre,
    )
    st.pyplot(fig)

    p_on_a = electronfactors.convert2_ratio_perim_area(width, length)

    try:
        width_data, factor_data, p_on_a_data = _load_reference_model(
            energy, applicator, ssd
        )
    except ValueError:
        return

    model_factor = electronfactors.spline_model_with_deformability(
        width,
        p_on_a,
        width_data,
        p_on_a_data,
        factor_data,
    )[0]

    st.write(f"Factor: `{model_factor}`")


def _plot_insert(insert_x, insert_y, width, length, circle_centre):
    circle, ellipse = _visual_circle_and_ellipse(
        insert_x, insert_y, width, length, circle_centre
    )

    plt.figure()
    plt.plot(insert_x, insert_y)
    plt.axis("equal")

    plt.plot(circle["x"], circle["y"])
    plt.title("Insert shape parameterisation")
    plt.xlabel("x (cm)")
    plt.ylabel("y (cm)")
    plt.grid(True)

    plt.plot(ellipse["x"], ellipse["y"])


def _visual_circle_and_ellipse(insert_x, insert_y, width, length, circle_centre):
    t = np.linspace(0, 2 * np.pi)
    circle = {
        "x": width / 2 * np.sin(t) + circle_centre[0],
        "y": width / 2 * np.cos(t) + circle_centre[1],
    }

    (
        x_shift,
        y_shift,
        rotation_angle,
    ) = electronfactors.visual_alignment_of_equivalent_ellipse(
        insert_x, insert_y, width, length, None
    )

    rotation_matrix = np.array(
        [
            [np.cos(rotation_angle), -np.sin(rotation_angle)],
            [np.sin(rotation_angle), np.cos(rotation_angle)],
        ]
    )

    ellipse = np.array([length / 2 * np.sin(t), width / 2 * np.cos(t)]).T

    rotated_ellipse = ellipse @ rotation_matrix

    translated_ellipse = rotated_ellipse + np.array([y_shift, x_shift])
    ellipse = {"x": translated_ellipse[:, 1], "y": translated_ellipse[:, 0]}

    return circle, ellipse


# TODO: Use config here
def _load_reference_model(energy, applicator, ssd):
    data_filename = r"S:\Physics\RCCC Specific Files\Dosimetry\Elekta_EFacs\electron_factor_measured_data.csv"
    data = pd.read_csv(data_filename)

    reference = (
        (data["Energy (MeV)"] == energy)
        & (data["Applicator (cm)"] == applicator)
        & (data["SSD (cm)"] == ssd)
    )

    width_data = data["Width (cm @ 100SSD)"][reference]
    length_data = data["Length (cm @ 100SSD)"][reference]
    factor_data = data["RCCC Inverse factor (dose open / dose cutout)"][reference]

    p_on_a_data = electronfactors.convert2_ratio_perim_area(width_data, length_data)

    reference_data_table = pd.concat(
        [width_data, length_data, factor_data],
        axis=1,
    )
    reference_data_table.sort_values(
        ["RCCC Inverse factor (dose open / dose cutout)"],
        ascending=False,
        inplace=True,
    )
    st.write(reference_data_table)

    number_of_measurements = np.sum(reference)
    if number_of_measurements < 8:
        fig, ax = plt.subplots()
        scat = ax.scatter(
            width_data,
            length_data,
            s=100,
            c=factor_data,
            cmap="viridis",
            zorder=2,
        )
        fig.colorbar(scat)

        raise ValueError("Not enough data points")

    fig = _plot_model(
        width_data,
        length_data,
        factor_data,
    )

    st.pyplot(fig)

    return width_data, factor_data, p_on_a_data


def _plot_model(width_data, length_data, factor_data):
    i, j, k = electronfactors.create_transformed_mesh(
        width_data, length_data, factor_data
    )
    model_width, model_length, model_factor = i, j, k

    vmin = np.nanmin(np.concatenate([model_factor.ravel(), factor_data.ravel()]))
    vmax = np.nanmax(np.concatenate([model_factor.ravel(), factor_data.ravel()]))

    fig, ax = plt.subplots()

    scat = ax.scatter(
        width_data,
        length_data,
        s=100,
        c=factor_data,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        zorder=2,
    )

    fig.colorbar(scat)

    cs = ax.contour(model_width, model_length, model_factor, 20, vmin=vmin, vmax=vmax)

    ax.clabel(cs, cs.levels[::2], inline=True)

    ax.set_title("Insert model")
    ax.set_xlabel("width (cm)")
    ax.set_ylabel("length (cm)")

    return fig
