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

from . import createaxis, imginterp, interppoints


def image_analysis_figure(
    x,
    y,
    img,
    bb_centre,
    field_centre,
    field_rotation,
    bb_diameter,
    edge_lengths,
    penumbra,
    units="(mm)",
):
    field = imginterp.create_interpolated_field(x, y, img)

    x_half_bound = edge_lengths[0] / 2 + penumbra * 3
    y_half_bound = edge_lengths[1] / 2 + penumbra * 3

    x_axis = np.linspace(-x_half_bound, x_half_bound, 200)
    y_axis = np.linspace(-y_half_bound, y_half_bound, 200)

    field_transform = interppoints.translate_and_rotate_transform(
        field_centre, field_rotation
    )
    x_field_interp, y_field_interp = createaxis.transform_axis(
        x_axis, y_axis, field_transform
    )

    if bb_centre is not None:
        bb_transform = interppoints.translate_and_rotate_transform(bb_centre, 0)
        x_bb_interp, y_bb_interp = createaxis.transform_axis(
            x_axis, y_axis, bb_transform
        )
    else:
        x_bb_interp, y_bb_interp = None, None

    fig, axs = plt.subplots(ncols=2, nrows=4, figsize=(12, 15))
    gs = axs[0, 0].get_gridspec()
    for ax in np.ravel(axs[0:2, 0:2]):
        ax.remove()

    ax_big = fig.add_subplot(gs[0:2, 0:2])

    axs[0, 0] = ax_big

    pixel_value_label = "Scaled image pixel value"

    image_with_overlays(
        fig,
        ax_big,
        x,
        y,
        img,
        field_transform,
        bb_centre,
        field_centre,
        bb_diameter,
        edge_lengths,
        x_field_interp,
        y_field_interp,
        x_bb_interp,
        y_bb_interp,
        pixel_value_label,
        units=units,
    )

    profile_flip_plot(axs[2, 0], x_axis, field(*x_field_interp))
    axs[2, 0].set_xlim(
        [edge_lengths[0] / 2 - penumbra * 2, edge_lengths[0] / 2 + penumbra * 2]
    )
    axs[2, 0].set_title("Flipped profile about field centre [field x-axis]")
    axs[2, 0].set_xlabel(f"Distance from field centre {units}")
    axs[2, 0].set_ylabel(pixel_value_label)

    profile_flip_plot(axs[2, 1], y_axis, field(*y_field_interp))
    axs[2, 1].set_xlim(
        [edge_lengths[1] / 2 - penumbra * 2, edge_lengths[1] / 2 + penumbra * 2]
    )
    axs[2, 1].set_title("Flipped profile about field centre [field y-axis]")
    axs[2, 1].set_xlabel(f"Distance from field centre {units}")
    axs[2, 1].set_ylabel(pixel_value_label)

    if bb_centre is not None:
        x_mask = (x_axis >= -bb_diameter / 2 - penumbra) & (
            x_axis <= bb_diameter / 2 + penumbra
        )
        profile_flip_plot(axs[3, 0], x_axis[x_mask], field(*x_bb_interp)[x_mask])
        axs[3, 0].set_xlim([-bb_diameter / 2 - penumbra, bb_diameter / 2 + penumbra])
        axs[3, 0].set_title("Flipped profile about BB centre [panel x-axis]")
        axs[3, 0].set_xlabel(f"Displacement from BB centre {units}")
        axs[3, 0].set_ylabel(pixel_value_label)

        y_mask = (y_axis >= -bb_diameter / 2 - penumbra) & (
            y_axis <= bb_diameter / 2 + penumbra
        )
        profile_flip_plot(axs[3, 1], y_axis[y_mask], field(*y_bb_interp)[y_mask])
        axs[3, 1].set_xlim([-bb_diameter / 2 - penumbra, bb_diameter / 2 + penumbra])
        axs[3, 1].set_title("Flipped profile about BB centre [panel y-axis]")
        axs[3, 1].set_xlabel(f"Displacement from BB centre {units}")
        axs[3, 1].set_ylabel(pixel_value_label)

    plt.tight_layout()

    return fig, axs


def profile_flip_plot(ax, dependent, independent):
    ax.plot(dependent, independent)
    ax.plot(-dependent, independent)


def image_with_overlays(
    fig,
    ax,
    x,
    y,
    img,
    field_transform,
    bb_centre,
    field_centre,
    bb_diameter,
    edge_lengths,
    x_field_interp,
    y_field_interp,
    x_bb_interp,
    y_bb_interp,
    pixel_value_label,
    units="(mm)",
):
    rect_crosshair_dx = [
        -edge_lengths[0] / 2,
        edge_lengths[0],
        -edge_lengths[0],
        edge_lengths[0],
    ]
    rect_crosshair_dy = [-edge_lengths[1] / 2, edge_lengths[1], 0, -edge_lengths[1]]

    rect_dx = [-edge_lengths[0] / 2, 0, edge_lengths[0], 0, -edge_lengths[0]]
    rect_dy = [-edge_lengths[1] / 2, edge_lengths[1], 0, -edge_lengths[1], 0]

    c = ax.contourf(x, y, img, 100)
    fig.colorbar(c, ax=ax, label=pixel_value_label)

    ax.plot(*draw_by_diff(rect_dx, rect_dy, field_transform), "k", lw=3)
    ax.plot(
        *draw_by_diff(rect_crosshair_dx, rect_crosshair_dy, field_transform), "k", lw=1
    )

    ax.plot(x_field_interp[0], x_field_interp[1], "k", lw=0.5, alpha=0.3)
    ax.plot(y_field_interp[0], y_field_interp[1], "k", lw=0.5, alpha=0.3)

    if bb_centre is not None:
        bb_radius = bb_diameter / 2
        bb_crosshair = np.array([-bb_radius, bb_radius])

        t = np.linspace(0, 2 * np.pi)
        circle_x_origin = bb_diameter / 2 * np.sin(t)
        circle_y_origin = bb_diameter / 2 * np.cos(t)

        circle_x = circle_x_origin + bb_centre[0]
        circle_y = circle_y_origin + bb_centre[1]

        ax.plot([bb_centre[0]] * 2, bb_crosshair + bb_centre[1], "k", lw=1)
        ax.plot(bb_crosshair + bb_centre[0], [bb_centre[1]] * 2, "k", lw=1)

        ax.plot(circle_x, circle_y, "k", lw=3)

        ax.plot(x_bb_interp[0], x_bb_interp[1], "k", lw=0.5, alpha=0.3)
        ax.plot(y_bb_interp[0], y_bb_interp[1], "k", lw=0.5, alpha=0.3)

        ax.plot(
            [field_centre[0], bb_centre[0]],
            [field_centre[1], bb_centre[1]],
            c="C3",
            lw=3,
        )

    ax.axis("equal")
    long_edge = np.sqrt(np.sum((np.array(edge_lengths)) ** 2))
    long_edge_fraction = long_edge * 0.6

    ax.set_xlim(
        [field_centre[0] - long_edge_fraction, field_centre[0] + long_edge_fraction]
    )
    ax.set_ylim(
        [field_centre[1] - long_edge_fraction, field_centre[1] + long_edge_fraction]
    )

    ax.set_xlabel(f"iView panel absolute x-pos {units}")
    ax.set_ylabel(f"iView panel absolute y-pos {units}")


def draw_by_diff(dx, dy, transform):
    draw_x = np.cumsum(dx)
    draw_y = np.cumsum(dy)

    draw_x, draw_y = interppoints.apply_transform(draw_x, draw_y, transform)

    return draw_x, draw_y
