from pymedphys._imports import numpy as np
from pymedphys._imports.slow import tensorflow as tf


def unet(
    grid_size,
    output_channels,
    max_filter_num=None,
    number_of_filters_start=32,
    min_grid_size=8,
    num_of_fc=2,
):
    inputs = tf.keras.layers.Input((grid_size, grid_size, 1))
    x = inputs
    skips = []

    (
        encode_layer_filter_numbers,
        encode_layer_dropout,
        decode_layer_filter_numbers,
        decode_layer_dropout,
    ) = _get_unet_parameters(
        grid_size, max_filter_num, number_of_filters_start, min_grid_size
    )

    for number_of_filters, dropout_rate in zip(
        encode_layer_filter_numbers, encode_layer_dropout
    ):
        x, skip = encode(
            x, number_of_filters=number_of_filters, dropout_rate=dropout_rate
        )
        skips.append(skip)

    skips.reverse()

    if num_of_fc is not None:
        input_output_channels_of_fc_layer = encode_layer_filter_numbers[-1]
        dense_channels = input_output_channels_of_fc_layer * 4
        if not max_filter_num is None and dense_channels > max_filter_num:
            dense_channels = max_filter_num

        x = _fully_connected_bottom(
            x,
            dense_channels,
            min_grid_size,
            input_output_channels_of_fc_layer,
            num_of_fc=num_of_fc,
        )

    for skip, number_of_filters, dropout_rate in zip(
        skips, decode_layer_filter_numbers, decode_layer_dropout
    ):
        x = decode(
            x, skip, number_of_filters=number_of_filters, dropout_rate=dropout_rate
        )

    x = tf.keras.layers.Conv2D(
        output_channels,
        1,
        activation="sigmoid",
        padding="same",
        kernel_initializer="he_normal",
    )(x)

    model = tf.keras.Model(inputs=inputs, outputs=x)

    return model


def _fully_connected_bottom(
    x,
    dense_channels,
    min_grid_size,
    input_output_channels_of_fc_layer,
    num_of_fc=2,
    batch_normalisation=True,
):
    start = x
    x = tf.keras.layers.Conv2D(
        dense_channels, min_grid_size, padding="valid", kernel_initializer="he_normal"
    )(x)
    for _ in range(num_of_fc):
        residual = x
        x = _batch_normalisation(x, batch_normalisation)
        x = _activation(x)
        x = tf.keras.layers.Dense(dense_channels)(x)
        x = tf.keras.layers.Add()([residual, x])

    x = _batch_normalisation(x, batch_normalisation)
    x = _activation(x)
    x = tf.keras.layers.Dense(
        input_output_channels_of_fc_layer * min_grid_size * min_grid_size
    )(x)
    x = tf.keras.layers.Reshape(
        (min_grid_size, min_grid_size, input_output_channels_of_fc_layer)
    )(x)
    x = tf.keras.layers.Add()([start, x])
    return x


def _get_unet_parameters(
    grid_size, max_filter_num=None, number_of_filters_start=32, min_grid_size=8
):
    drop_out_rate_start = 0.2
    drop_out_rate_step = 0.1
    drop_out_rate_max = 0.4

    number_of_encode_layers = np.log2(grid_size / min_grid_size)
    if number_of_encode_layers != round(number_of_encode_layers):
        raise ValueError("Grid size must be a power of 2 >= 16")

    number_of_encode_layers = int(number_of_encode_layers)

    encode_layer_filter_numbers = [number_of_filters_start]
    for i in range(1, number_of_encode_layers):
        previous = encode_layer_filter_numbers[i - 1]
        new = previous * 2

        if (not max_filter_num is None) and (new > max_filter_num):
            new = max_filter_num

        encode_layer_filter_numbers.append(new)

    encode_layer_dropout = []
    for i in range(number_of_encode_layers):
        dropout = drop_out_rate_start + drop_out_rate_step * i
        if dropout > drop_out_rate_max:
            dropout = drop_out_rate_max

        encode_layer_dropout.append(dropout)

    number_of_decode_layers = number_of_encode_layers

    decode_starting_filters = encode_layer_filter_numbers[-1] * 2
    if (not max_filter_num is None) and (decode_starting_filters > max_filter_num):
        decode_starting_filters = max_filter_num

    decode_layer_filter_numbers = [decode_starting_filters]
    for i in range(1, number_of_decode_layers):
        previous = decode_layer_filter_numbers[i - 1]
        new = previous / 2

        if new < number_of_filters_start:
            new = number_of_filters_start

        decode_layer_filter_numbers.append(new)

    decode_layer_dropout = [drop_out_rate_max] * number_of_decode_layers

    return (
        encode_layer_filter_numbers,
        encode_layer_dropout,
        decode_layer_filter_numbers,
        decode_layer_dropout,
    )


def encode(
    x,
    number_of_filters,
    number_of_convolutions=2,
    kernel_size=3,
    dropout_rate=1.0,
    pool=True,
    batch_normalisation=True,
):
    x = _convolutions(
        x, number_of_filters, number_of_convolutions, kernel_size, batch_normalisation
    )
    skip = x
    x = _dropout(x, dropout_rate)

    if pool is True:
        x = tf.keras.layers.MaxPool2D()(x)
        x = _batch_normalisation(x, batch_normalisation)
        x = _activation(x)

    return x, skip


def decode(
    x,
    skip,
    number_of_filters,
    number_of_convolutions=2,
    kernel_size=3,
    dropout_rate=1.0,
    batch_normalisation=False,
):
    x = _conv_transpose(x, number_of_filters, kernel_size)
    x = _batch_normalisation(x, batch_normalisation)
    x = _activation(x)

    x = tf.keras.layers.concatenate([skip, x], axis=3)

    x = _convolutions(
        x, number_of_filters, number_of_convolutions, kernel_size, batch_normalisation
    )
    x = _dropout(x, dropout_rate)

    return x


def _convolutions(
    x, number_of_filters, number_of_convolutions, kernel_size, batch_normalisation
):
    for _ in range(number_of_convolutions):
        x = _convolution(x, number_of_filters, kernel_size)
        x = _batch_normalisation(x, batch_normalisation)
        x = _activation(x)

    return x


def _convolution(x, number_of_filters, kernel_size):
    x = tf.keras.layers.Conv2D(
        number_of_filters, kernel_size, padding="same", kernel_initializer="he_normal"
    )(x)

    return x


def _activation(x):
    x = tf.keras.layers.Activation("relu")(x)

    return x


def _batch_normalisation(x, batch_normalisation):
    if batch_normalisation is True:
        x = tf.keras.layers.BatchNormalization()(x)

    return x


def _dropout(x, dropout_rate):
    if dropout_rate != 1.0:
        x = tf.keras.layers.Dropout(dropout_rate)(x)

    return x


def _conv_transpose(x, number_of_filters, kernel_size):
    x = tf.keras.layers.Conv2DTranspose(
        number_of_filters,
        kernel_size,
        strides=2,
        padding="same",
        kernel_initializer="he_normal",
    )(x)

    return x
