import functools

import matplotlib.pyplot as plt

import tensorflow as tf


@tf.function
def reduce_expanded_mask(expanded_mask, img_size, expansion):
    expanded_mask = tf.dtypes.cast(expanded_mask, tf.float32)
    return tf.reduce_mean(
        tf.reduce_mean(
            tf.reshape(expanded_mask, (img_size, expansion, img_size, expansion)),
            axis=1,
        ),
        axis=2,
    )


@tf.function
def get_circle_mask(bb_centre, bb_radius_sqrd, img_size, expansion):
    _, _, xx_expand, yy_expand = get_grids(img_size, expansion)
    expanded_mask = (xx_expand - bb_centre[0]) ** 2 + (
        yy_expand - bb_centre[1]
    ) ** 2 <= bb_radius_sqrd

    circle_mask = reduce_expanded_mask(expanded_mask, img_size, expansion)
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
    img_size = 128
    expansion = 16

    x, y, _, _ = get_grids(img_size, expansion)

    bb_diameter = 8.0
    bb_radius_sqrd = (bb_diameter / 2) ** 2

    circle_mask = get_circle_mask([60.5, 20.1], bb_radius_sqrd, img_size, expansion)

    plt.pcolormesh(x - 0.5, y - 0.5, circle_mask)
    plt.axis("equal")
    plt.show()


if __name__ == "__main__":
    main()
