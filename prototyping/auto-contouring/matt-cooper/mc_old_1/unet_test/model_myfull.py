import tensorflow as tf


def down_block(x, m, n, c):
    crop = tf.keras.layers.Cropping3D(cropping=(n, 0, 0))(x)
    crop = tf.keras.layers.Conv3D(c, 1, activation=None)(crop)

    result = tf.keras.layers.ReLU()(x)
    for repeat in range(m):
        result = tf.keras.layers.Conv3D(c, (1, 3, 3), strides=1, padding="same")(result)
        result = tf.keras.layers.ReLU()(result)

    for repeat in range(n):
        result = tf.keras.layers.Conv3D(c, (1, 3, 3), strides=1, padding="same")(result)
        result = tf.keras.layers.Conv3D(c, (3, 1, 1), strides=1, padding="valid")(
            result
        )
        if repeat != range(n)[-1]:
            result = tf.keras.layers.ReLU()(result)

    result = tf.keras.layers.Add()([crop, result])
    return result


def pool(x):
    result = tf.keras.layers.AveragePooling3D(
        pool_size=(1, 2, 2), strides=None, padding="valid"
    )(x)
    return result


def fc_block(x, r):
    initializer = tf.random_normal_initializer(0.0, 0.02)
    result = tf.keras.layers.Conv3D(1024, (1, 8, 8), strides=1, padding="valid")(x)
    for repeat in range(r):
        crop = result
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


def upscale(x):
    result = tf.keras.layers.UpSampling3D(size=(1, 2, 2))(x)
    return result


def stack(x, skip):
    # NOTE axis 0 is the batch
    result = tf.keras.layers.Concatenate(axis=1)([x, skip])
    return result


def Model(input_shape, output_channels):
    input_shape = [21, 512, 512, 1]
    inputs = tf.keras.layers.Input(shape=input_shape)
    skips = []

    x = down_block(inputs, 3, 0, 32)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 3, 0, 32)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 3, 0, 64)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 1, 2, 64)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 1, 2, 128)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 1, 2, 128)
    skips.append(x)
    x = pool(x)

    x = down_block(x, 0, 4, 256)
    skips.append(x)

    x = fc_block(x, 2)

    x = stack(skips[-1], x)
    x = up_block(x, 4, 128)

    x = upscale(x)
    x = stack(skips[-2], x)
    x = up_block(x, 4, 128)

    x = upscale(x)
    x = stack(skips[-3], x)
    x = up_block(x, 4, 64)

    x = upscale(x)
    x = stack(skips[-4], x)
    x = up_block(x, 3, 64)

    x = upscale(x)
    x = stack(skips[-5], x)
    x = up_block(x, 3, 32)

    x = upscale(x)
    x = stack(skips[-6], x)
    x = up_block(x, 3, 32)

    x = upscale(x)
    x = stack(skips[-7], x)
    x = up_block(x, 3, 32)

    x = tf.keras.layers.Conv3D(
        filters=output_channels,
        kernel_size=(1, 1, 1),
        strides=1,
        activation="sigmoid",
        padding="same",
    )(x)

    return tf.keras.Model(inputs=inputs, outputs=x)
