import tensorflow as tf


def Model(input_shape, output_channels):
    inputs = tf.keras.layers.Input(shape=input_shape)
    x = tf.keras.layers.Conv3D(1, (3, 3, 3), padding="same")(inputs)
    x = tf.keras.layers.AveragePooling3D(
        pool_size=(21, 1, 1), strides=1, padding="valid"
    )(x)
    x = tf.keras.layers.Conv3D(output_channels, 1, activation="sigmoid")(x)
    x = tf.keras.activations.sigmoid(x)
    return tf.keras.Model(inputs=inputs, outputs=x)
