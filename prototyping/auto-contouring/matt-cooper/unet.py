import tensorflow as tf


def Network(grid_size=512, output_channels=1):
    def encode(x, convs, filters, kernel, drop=False, pool=True, norm=True):
        # Convolution
        for _ in range(convs):
            x = tf.keras.layers.Conv2D(
                filters, kernel, padding="same", kernel_initializer="he_normal"
            )(x)
            if norm is True:
                x = tf.keras.layers.BatchNormalization()(x)
            x = tf.keras.layers.Activation("relu")(x)

        # Skips
        skip = x

        # Regularise and down-sample
        if drop is True:
            x = tf.keras.layers.Dropout(0.2)(x)
        if pool is True:
            x = tf.keras.layers.Conv2D(
                filters,
                kernel,
                strides=2,
                padding="same",
                kernel_initializer="he_normal",
            )(x)
            if norm is True:
                x = tf.keras.layers.BatchNormalization()(x)
            x = tf.keras.layers.Activation("relu")(x)

        return x, skip

    def decode(x, skip, convs, filters, kernel, drop=False, norm=False):
        # Up-convolution
        x = tf.keras.layers.Conv2DTranspose(
            filters, kernel, strides=2, padding="same", kernel_initializer="he_normal"
        )(x)

        if norm is True:
            x = tf.keras.layers.BatchNormalization()(x)

        x = tf.keras.layers.Activation("relu")(x)

        # Concat with skip
        x = tf.keras.layers.concatenate([skip, x], axis=3)

        # Convolution
        for _ in range(convs):
            x = tf.keras.layers.Conv2D(
                filters, kernel, padding="same", kernel_initializer="he_normal"
            )(x)
            if norm is True:
                x = tf.keras.layers.BatchNormalization()(x)

            x = tf.keras.layers.Activation("relu")(x)

        if drop is True:
            x = tf.keras.layers.Dropout(0.2)(x)

        return x

    inputs = tf.keras.layers.Input((grid_size, grid_size, 1))

    encoder_args = [
        # convs, filter, kernel, drop, pool, norm
        (2, 32, 3, False, True, True),  # 256, 32
        (2, 64, 3, False, True, True),  # 128, 64
        (2, 128, 3, False, True, True),  # 64, 128
        (2, 256, 3, False, True, True),  # 32, 256
        (2, 512, 3, False, True, True),  # 16, 512
        (2, 1024, 3, False, True, True),  # 8, 1024
    ]

    decoder_args = [
        # convs, filter, kernel, drop, norm
        (2, 512, 3, True, True),  # 16, 512
        (2, 256, 3, True, True),  # 32, 256
        (2, 128, 3, False, True),  # 64, 128
        (2, 64, 3, False, True),  # 128, 64
        (2, 32, 3, False, True),  # 256, 32
        (2, 16, 3, False, True),  # 512, 16
    ]

    outputs = tf.keras.layers.Conv2D(
        output_channels,
        1,
        activation="sigmoid",
        padding="same",
        kernel_initializer="he_normal",
    )
    x = inputs
    skips = []

    for args in encoder_args:
        x, skip = encode(x, *args)
        skips.append(skip)

    skips.reverse()

    for skip, args in zip(skips, decoder_args):
        x = decode(x, skip, *args)

    x = outputs(x)

    return tf.keras.Model(inputs=inputs, outputs=x)
