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

import pathlib
import re

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

import pymedphys
import pymedphys._electronfactors as electronfactors
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import monaco as st_monaco

# Old code warning, the below is Simon Biggs from 2015... be nice to him

CATEGORY = categories.ALPHA
TITLE = "Electron Insert Factor Modelling"


def main():
    demo_mode = _set_parameters()
    config = _get_config(demo_mode)

    telfile_picker_results = st_monaco.monaco_tel_files_picker(config)
    monaco_directory, tel_paths = [
        telfile_picker_results[key]
        for key in (
            "monaco_directory",
            "tel_paths",
        )
    ]

    if st.button("Calculate"):
        for filepath in tel_paths:
            st.write("---")
            st.write(f"## Tel file: `{filepath.relative_to(monaco_directory)}`")

            _logic_per_telfile(config, filepath)


def _set_parameters():
    st.sidebar.write("# Configuration")

    DEMO_MODE_LABEL = "Demo configuration file"

    try:
        _get_config(False)
        config_options = ["Config on disk", DEMO_MODE_LABEL]
    except FileNotFoundError:
        config_options = [DEMO_MODE_LABEL]

    config_selection = st.sidebar.radio("Config file to use", options=config_options)
    demo_mode = config_selection == DEMO_MODE_LABEL

    return demo_mode


@st.cache
def _download_demo_data():
    cwd = pathlib.Path.cwd()
    pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip", extract_directory=cwd)

    return cwd.joinpath("pymedphys-gui-demo")


@st.cache
def _get_config(demo_mode):
    if demo_mode:
        path = _download_demo_data()
    else:
        path = None

    return _config.get_config(path)


def _logic_per_telfile(config, filepath):
    with open(filepath, "r") as file:
        tel_contents = np.array(file.read().splitlines())

    model_name_pattern = _get_beam_model_name_pattern(config)

    reference_indices = []
    for i, item in enumerate(tel_contents):
        if re.search(model_name_pattern, item):
            reference_indices.append(i)

    if len(reference_indices) == 0:
        st.info("No electron plans found within this tel file")

    for reference_index in reference_indices:
        _per_reference_index(config, tel_contents, reference_index)


def _per_reference_index(config, tel_contents, reference_index):
    model_name_pattern = _get_beam_model_name_pattern(config)
    applicator_pattern = _get_applicator_pattern(config)

    applicator = float(
        re.search(applicator_pattern, tel_contents[reference_index + 12]).group(1)
    )
    energy = float(
        re.search(model_name_pattern, tel_contents[reference_index]).group(1)
    )
    ssd = 100

    st.write(f"### Applicator: `{applicator} cm` | Energy: `{energy} MeV`")

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

    left, right = st.beta_columns(2)

    with left:
        st.write("#### Insert parameterisation")

        fig = _plot_insert(
            x,
            y,
            width,
            length,
            circle_centre,
        )
        st.pyplot(fig)

        st.write(f"Width: `{width:.2f} cm`")
        st.write(f"Length: `{length:.2f} cm`")

    p_on_a = electronfactors.convert2_ratio_perim_area(width, length)

    with right:
        st.write("#### Insert factor modelling")
        try:
            width_data, factor_data, p_on_a_data = _load_reference_model(
                config, energy, applicator, ssd
            )
        except ValueError:
            return

        model_factor = electronfactors.spline_model_with_deformability(
            width,
            p_on_a,
            width_data,
            p_on_a_data,
            factor_data,
        )

    st.write(f"Factor: `{model_factor:.4f}`")


def _plot_insert(insert_x, insert_y, width, length, circle_centre):
    circle, ellipse = _visual_circle_and_ellipse(
        insert_x, insert_y, width, length, circle_centre
    )

    fig, ax = plt.subplots()

    ax.plot(insert_x, insert_y, label="Clinical insert")

    ax.plot(circle["x"], circle["y"], label="Largest fully encompassed circle")
    ax.set_title("Insert shape parameterisation")
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.grid(True)

    ax.plot(
        ellipse["x"], ellipse["y"], label="Ellipse with approximately equivalent factor"
    )
    ax.axis("equal")
    ax.legend()

    return fig


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


def _load_reference_model(config, energy, applicator, ssd):
    data_filename = _get_data_path(config)
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

    number_of_measurements = np.sum(reference)
    not_enough_data_points = number_of_measurements < 8

    if not_enough_data_points:
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
    else:
        fig = _plot_model(
            width_data,
            length_data,
            factor_data,
        )

    st.pyplot(fig)

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

    if not_enough_data_points:
        raise ValueError("Not enough data points")

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


def _get_data_path(config):
    return config["electron_insert_modelling"]["data_path"]


def _get_beam_model_name_pattern(config):
    return config["electron_insert_modelling"]["patterns"]["beam_model_name"]


def _get_applicator_pattern(config):
    return config["electron_insert_modelling"]["patterns"]["applicator"]
