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

import pymedphys._electronfactors as electronfactors
from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc as _misc

# Old code warning, the below is Simon Biggs from 2015... be nice to him

CATEGORY = categories.ALPHA
TITLE = "Electron Insert Factor Modelling"


def visual_circle_and_ellipse(insert_x, insert_y, width, length, circle_centre):
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


def plot_insert(insert_x, insert_y, width, length, circle_centre):
    circle, ellipse = visual_circle_and_ellipse(
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


def plot_model(width_data, length_data, factor_data):
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


def main():
    config = _config.get_config()
    clinical_directory = _get_clinical_directory(config)

    patient_id = st.text_input("Patient ID")

    if patient_id == "":
        st.stop()

    tel_filepaths = list(clinical_directory.glob(f"*~{patient_id}/plan/*/*tel.1"))

    electronmodel_regex = r"RiverinaAgility - (\d+)MeV"
    applicator_regex = r"(\d+)X\d+"

    insert_data = dict()  # type: ignore

    for telfilepath in tel_filepaths:
        insert_data[telfilepath] = dict()

        with open(telfilepath, "r") as file:
            telfilecontents = np.array(file.read().splitlines())

        insert_data[telfilepath]["reference_index"] = []
        for i, item in enumerate(telfilecontents):
            if re.search(electronmodel_regex, item):
                insert_data[telfilepath]["reference_index"] += [i]

        insert_data[telfilepath]["applicators"] = [
            re.search(applicator_regex, telfilecontents[i + 12]).group(
                1
            )  # type: ignore
            for i in insert_data[telfilepath]["reference_index"]
        ]

        insert_data[telfilepath]["energies"] = [
            re.search(electronmodel_regex, telfilecontents[i]).group(1)  # type: ignore
            for i in insert_data[telfilepath]["reference_index"]
        ]

    for telfilepath in tel_filepaths:
        with open(telfilepath, "r") as file:
            telfilecontents = np.array(file.read().splitlines())

        insert_data[telfilepath]["x"] = []
        insert_data[telfilepath]["y"] = []

        for i, index in enumerate(insert_data[telfilepath]["reference_index"]):
            insert_initial_range = telfilecontents[
                index + 51 : :
            ]  # coords start 51 lines after electron model name
            insert_stop = np.where(insert_initial_range == "0")[0][
                0
            ]  # coords stop right before a line containing 0

            insert_coords_string = insert_initial_range[:insert_stop]
            insert_coords = np.fromstring(",".join(insert_coords_string), sep=",")
            insert_data[telfilepath]["x"].append(insert_coords[0::2] / 10)
            insert_data[telfilepath]["y"].append(insert_coords[1::2] / 10)

    for telfilepath in tel_filepaths:
        insert_data[telfilepath]["width"] = []
        insert_data[telfilepath]["length"] = []
        insert_data[telfilepath]["circle_centre"] = []
        insert_data[telfilepath]["P/A"] = []

        for i in range(len(insert_data[telfilepath]["reference_index"])):

            width, length, circle_centre = electronfactors.parameterise_insert(
                insert_data[telfilepath]["x"][i], insert_data[telfilepath]["y"][i]
            )

            insert_data[telfilepath]["width"].append(width)
            insert_data[telfilepath]["length"].append(length)
            insert_data[telfilepath]["circle_centre"].append(circle_centre)

            insert_data[telfilepath]["P/A"].append(
                electronfactors.convert2_ratio_perim_area(width, length)
            )

    data_filename = r"S:\Physics\RCCC Specific Files\Dosimetry\Elekta_EFacs\electron_factor_measured_data.csv"
    data = pd.read_csv(data_filename)

    width_data = data["Width (cm @ 100SSD)"]
    length_data = data["Length (cm @ 100SSD)"]
    factor_data = data["RCCC Inverse factor (dose open / dose cutout)"]

    p_on_a_data = electronfactors.convert2_ratio_perim_area(width_data, length_data)

    for telfilepath in tel_filepaths:
        insert_data[telfilepath]["model_factor"] = []

        for i in range(len(insert_data[telfilepath]["reference_index"])):
            applicator = float(insert_data[telfilepath]["applicators"][i])
            energy = float(insert_data[telfilepath]["energies"][i])
            ssd = 100

            reference = (
                (data["Energy (MeV)"] == energy)
                & (data["Applicator (cm)"] == applicator)
                & (data["SSD (cm)"] == ssd)
            )

            number_of_measurements = np.sum(reference)

            if number_of_measurements < 8:
                insert_data[telfilepath]["model_factor"].append(np.nan)
            else:
                insert_data[telfilepath]["model_factor"].append(
                    electronfactors.spline_model_with_deformability(
                        insert_data[telfilepath]["width"],
                        insert_data[telfilepath]["P/A"],
                        width_data[reference],
                        p_on_a_data[reference],
                        factor_data[reference],
                    )[0]
                )

    for telfilepath in tel_filepaths:
        st.write("---")
        st.write("Filepath: `{}`".format(telfilepath))

        for i in range(len(insert_data[telfilepath]["reference_index"])):
            applicator = float(insert_data[telfilepath]["applicators"][i])
            energy = float(insert_data[telfilepath]["energies"][i])
            ssd = 100

            st.write(
                "Applicator: `{} cm` | Energy: `{} MeV`".format(applicator, energy)
            )

            width = insert_data[telfilepath]["width"][i]
            length = insert_data[telfilepath]["length"][i]

            plt.figure()
            plot_insert(
                insert_data[telfilepath]["x"][i],
                insert_data[telfilepath]["y"][i],
                insert_data[telfilepath]["width"][i],
                insert_data[telfilepath]["length"][i],
                insert_data[telfilepath]["circle_centre"][i],
            )

            reference = (
                (data["Energy (MeV)"] == energy)
                & (data["Applicator (cm)"] == applicator)
                & (data["SSD (cm)"] == ssd)
            )

            number_of_measurements = np.sum(reference)

            if number_of_measurements < 8:
                fig, ax = plt.subplots()
                scat = ax.scatter(
                    width_data[reference],
                    length_data[reference],
                    s=100,
                    c=factor_data[reference],
                    cmap="viridis",
                    zorder=2,
                )
                fig.colorbar(scat)
            else:
                fig = plot_model(
                    width_data[reference],
                    length_data[reference],
                    factor_data[reference],
                )

            reference_data_table = pd.concat(
                [width_data[reference], length_data[reference], factor_data[reference]],
                axis=1,
            )
            reference_data_table.sort_values(
                ["RCCC Inverse factor (dose open / dose cutout)"],
                ascending=False,
                inplace=True,
            )

            st.write(reference_data_table)

            st.pyplot(fig)

            factor = insert_data[telfilepath]["model_factor"][i]

            st.write(
                "Width: `{0:0.2f} cm` | Length: `{1:0.2f} cm` | Factor: `{2:0.3f}`".format(
                    width, length, factor
                )
            )


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
