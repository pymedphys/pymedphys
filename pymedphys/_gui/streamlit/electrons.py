# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import re
from glob import glob

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import streamlit as st

import pymedphys.electronfactors as electronfactors

"""
# Electron Insert Factors
"""

patient_id = st.text_input("Patient ID")

if patient_id == "":
    st.stop()


rccc_string_search_pattern = r"\\monacoda\FocalData\RCCC\1~Clinical\*~{}\plan\*\*tel.1".format(
    patient_id
)
rccc_filepath_list = glob(rccc_string_search_pattern)

nbccc_string_search_pattern = r"\\tunnel-nbcc-monaco\FOCALDATA\NBCCC\1~Clinical\*~{}\plan\*\*tel.1".format(
    patient_id
)
nbccc_filepath_list = glob(nbccc_string_search_pattern)

sash_string_search_pattern = r"\\tunnel-sash-monaco\Users\Public\Documents\CMS\FocalData\SASH\1~Clinical\*~{}\plan\*\*tel.1".format(
    patient_id
)
sash_filepath_list = glob(sash_string_search_pattern)


filepath_list = np.concatenate(
    [rccc_filepath_list, nbccc_filepath_list, sash_filepath_list]
)


electronmodel_regex = r"RiverinaAgility - (\d+)MeV"
applicator_regex = r"(\d+)X\d+"

insert_data = dict()  # type: ignore

for telfilepath in filepath_list:
    insert_data[telfilepath] = dict()

    with open(telfilepath, "r") as file:
        telfilecontents = np.array(file.read().splitlines())

    insert_data[telfilepath]["reference_index"] = []
    for i, item in enumerate(telfilecontents):
        if re.search(electronmodel_regex, item):
            insert_data[telfilepath]["reference_index"] += [i]

    insert_data[telfilepath]["applicators"] = [
        re.search(applicator_regex, telfilecontents[i + 12]).group(1)  # type: ignore
        for i in insert_data[telfilepath]["reference_index"]
    ]

    insert_data[telfilepath]["energies"] = [
        re.search(electronmodel_regex, telfilecontents[i]).group(1)  # type: ignore
        for i in insert_data[telfilepath]["reference_index"]
    ]


for telfilepath in filepath_list:
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


for telfilepath in filepath_list:
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


for telfilepath in filepath_list:
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

    plt.scatter(
        width_data,
        length_data,
        s=100,
        c=factor_data,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        zorder=2,
    )

    plt.colorbar()

    cs = plt.contour(model_width, model_length, model_factor, 20, vmin=vmin, vmax=vmax)

    plt.clabel(cs, cs.levels[::2], inline=True)

    plt.title("Insert model")
    plt.xlabel("width (cm)")
    plt.ylabel("length (cm)")


for telfilepath in filepath_list:
    "======================================================================="
    st.write("Filepath: `{}`".format(telfilepath))

    for i in range(len(insert_data[telfilepath]["reference_index"])):
        applicator = float(insert_data[telfilepath]["applicators"][i])
        energy = float(insert_data[telfilepath]["energies"][i])
        ssd = 100

        st.write("Applicator: `{} cm` | Energy: `{} MeV`".format(applicator, energy))

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

        plt.figure()
        if number_of_measurements < 8:
            plt.scatter(
                width_data[reference],
                length_data[reference],
                s=100,
                c=factor_data[reference],
                cmap="viridis",
                zorder=2,
            )
            plt.colorbar()
        else:
            plot_model(
                width_data[reference], length_data[reference], factor_data[reference]
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

        reference_data_table

        st.pyplot()

        factor = insert_data[telfilepath]["model_factor"][i]

        st.write(
            "Width: `{0:0.2f} cm` | Length: `{1:0.2f} cm` | Factor: `{2:0.3f}`".format(
                width, length, factor
            )
        )
