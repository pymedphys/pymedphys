import functools

import numpy as np

import matplotlib.pyplot as plt

import tensorflow as tf


def reduce_expanded_mask(expanded_mask, img_size, expansion):
    expanded_mask = tf.dtypes.cast(expanded_mask, tf.float32)
    return tf.reduce_mean(
        tf.reduce_mean(
            tf.reshape(expanded_mask, (img_size, expansion, img_size, expansion)),
            axis=1,
        ),
        axis=2,
    )


def get_circle_mask(bb_centre, bb_radius_sqrd, img_size, expansion):
    _, _, xx_expand, yy_expand = get_grids(img_size, expansion)
    expanded_mask = (xx_expand - bb_centre[0]) ** 2 + (
        yy_expand - bb_centre[1]
    ) ** 2 <= bb_radius_sqrd

    circle_mask = reduce_expanded_mask(expanded_mask, img_size, expansion)
    return circle_mask * 2 - 1


def get_simple_circle_mask(bb_centre, bb_radius_sqrd, x, y):
    xx, yy = tf.meshgrid(x, y)

    circle_mask = (xx - bb_centre[0]) ** 2 + (yy - bb_centre[1]) ** 2 <= bb_radius_sqrd
    circle_mask = tf.dtypes.cast(circle_mask, tf.float32)

    return circle_mask * 2 - 1


@functools.lru_cache()
def get_grids(img_size, expansion):
    x = tf.range(0, img_size, dtype=tf.float32)
    y = tf.range(0, img_size, dtype=tf.float32)

    dx = 1 / expansion
    x_expand = tf.range(-0.5 + dx / 2, img_size - 0.5, dx)
    y_expand = tf.range(-0.5 + dx / 2, img_size - 0.5, dx)
    xx_expand, yy_expand = tf.meshgrid(x_expand, y_expand)

    return x, y, xx_expand, yy_expand


def main():
    img_size = 16
    expansion = 4

    x, y, _, _ = get_grids(img_size, expansion)

    bb_diameter = 6.0
    bb_radius = bb_diameter / 2
    bb_radius_sqrd = bb_radius ** 2

    bb_centre_1 = [4.5, 4.1]
    bb_centre_2 = [10.5, 10.1]

    circle_mask = get_circle_mask(bb_centre_1, bb_radius_sqrd, img_size, expansion)
    simple_circle_mask = get_simple_circle_mask(bb_centre_2, bb_radius_sqrd, x, y)

    total_mask = tf.stack([circle_mask, simple_circle_mask], axis=-1)
    total_mask = tf.reduce_sum(total_mask, axis=-1) + 1

    theta = tf.range(0, 2 * np.pi, 0.1)
    circle_x_base = tf.sin(theta) * bb_radius
    circle_y_base = tf.cos(theta) * bb_radius

    bb_1_x = circle_x_base + bb_centre_1[0]
    bb_1_y = circle_y_base + bb_centre_1[1]
    bb_2_x = circle_x_base + bb_centre_2[0]
    bb_2_y = circle_y_base + bb_centre_2[1]

    plt.pcolormesh(x - 0.5, y - 0.5, total_mask)
    plt.colorbar()

    plt.contour(x, y, total_mask, [0], cmap="bwr_r")
    plt.plot(bb_1_x, bb_1_y, "k--", alpha=0.5)
    plt.plot(bb_2_x, bb_2_y, "k--", alpha=0.5)

    plt.axis("equal")
    plt.show()


if __name__ == "__main__":
    main()
