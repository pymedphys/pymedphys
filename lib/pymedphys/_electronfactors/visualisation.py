# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import numpy as np
from pymedphys._imports import plt

from .core import (
    create_transformed_mesh,
    parameterise_insert_with_visual_alignment,
    visual_alignment_of_equivalent_ellipse,
)


def model_and_display(x, y):
    (width, length, circle_centre, _, _, _) = parameterise_insert_with_visual_alignment(
        x, y
    )

    plot_insert(x, y, width, length, circle_centre)

    return width, length


def visual_circle_and_ellipse(insert_x, insert_y, width, length, circle_centre):

    t = np.linspace(0, 2 * np.pi)
    circle = {
        "x": width / 2 * np.sin(t) + circle_centre[0],
        "y": width / 2 * np.cos(t) + circle_centre[1],
    }

    x_shift, y_shift, rotation_angle = visual_alignment_of_equivalent_ellipse(
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

    i, j, k = create_transformed_mesh(width_data, length_data, factor_data)
    model_width, model_length, model_factor = i, j, k

    # model_width_mesh, model_length_mesh = np.meshgrid(
    #     model_width, model_length)

    vmin = np.nanmin(np.concatenate([model_factor.ravel(), factor_data.ravel()]))
    vmax = np.nanmax(np.concatenate([model_factor.ravel(), factor_data.ravel()]))
    # vrange = vmax - vmin

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
