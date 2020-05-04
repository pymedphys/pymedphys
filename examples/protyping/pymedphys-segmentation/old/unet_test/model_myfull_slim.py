import tensorflow as tf


def down_block(x, m, n, c, size):
    Zc = int((n / 2) * (size - 1))
    crop = tf.keras.layers.Cropping3D(cropping=(Zc, 0, 0))(x)
    crop = tf.keras.layers.Conv3D(c, 1, activation=None)(crop)

    result = tf.keras.layers.ReLU()(x)
    for repeat in range(m):
        result = tf.keras.layers.Conv3D(c, (1, 3, 3), strides=1, padding="same")(result)
        result = tf.keras.layers.ReLU()(result)

    for repeat in range(n):
        result = tf.keras.layers.Conv3D(c, (1, 3, 3), strides=1, padding="same")(result)
        result = tf.keras.layers.Conv3D(c, (size, 1, 1), strides=1, padding="valid")(
            result
        )
        if repeat != range(n)[-1]:
            result = tf.keras.layers.ReLU()(result)

    result = tf.keras.layers.Add()([crop, result])

    return result


def pool(x, size):
    result = tf.keras.layers.AveragePooling3D(
        pool_size=(1, size, size), strides=None, padding="valid"
    )(x)
    return result


def fc_block(x, r):
    initializer = tf.random_normal_initializer(0.0, 0.02)
    result = tf.keras.layers.Conv3D(1024, (1, 8, 8), strides=1, padding="valid")(x)
    for repeat in range(r):
        crop = result
        # TODO: Should this be a dense layer with RelU activation instead?
        result = tf.keras.layers.ReLU()(result)
        result = tf.keras.layers.Add()([crop, result])

    result = tf.keras.layers.ReLU()(result)
    result = tf.keras.layers.Reshape((1, 8, 8, 256))(x)

    return result


def up_block(x, m, c):
    initializer = tf.random_normal_initializer(0.0, 0.02)

    crop = tf.keras.layers.Conv3D(c, 1, activation=None)(x)

    result = tf.keras.layers.ReLU()(x)
    for repeat in range(m):
        result = tf.keras.layers.Conv3D(c, (1, 3, 3), strides=1, padding="same")(result)
        result = tf.keras.layers.ReLU()(result)
    result = tf.keras.layers.Add()([crop, result])
    return result


def upscale(x, size):
    result = tf.keras.layers.UpSampling3D(size=(1, size, size))(x)
    return result


def stack(x, skip):
    # NOTE axis 0 is the batch
    result = tf.keras.layers.Concatenate(axis=1)([x, skip])
    return result


def Model(input_shape, output_channels):
    inputs = tf.keras.layers.Input(shape=input_shape)
    skips = []

    x = down_block(inputs, 0, 2, 64, 5)
    skips.append(x)
    x = pool(x, 4)

    x = down_block(x, 0, 2, 128, 4)
    skips.append(x)
    x = pool(x, 4)

    x = down_block(x, 0, 2, 256, 4)
    skips.append(x)
    x = pool(x, 4)

    x = fc_block(x, 2)

    x = upscale(x, 4)
    x = stack(skips[-1], x)
    x = up_block(x, 1, 128)

    x = upscale(x, 4)
    x = stack(skips[-2], x)
    x = up_block(x, 1, 64)

    x = upscale(x, 4)
    x = stack(skips[-3], x)
    x = up_block(x, 1, 1)

    x = tf.keras.layers.Conv3D(
        filters=output_channels,
        kernel_size=(22, 1, 1),
        strides=1,
        activation="sigmoid",
        padding="valid",
    )(x)

    return tf.keras.Model(inputs=inputs, outputs=x)
