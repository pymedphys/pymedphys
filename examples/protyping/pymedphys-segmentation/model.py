import config
import tensorflow as tf

initializer = tf.random_normal_initializer(0.0, 0.02)


def down_block(x, depth, m, n, channels, pool):
    convolution_sequence = tf.keras.Sequential(name=f"down-convolution-d{depth}")
    convolution_sequence.add(tf.keras.layers.ReLU())
    for _ in range(m):
        convolution_sequence.add(
            tf.keras.layers.Conv3D(
                channels,
                (3, 3, 1),
                strides=1,
                padding="same",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )

    for i in range(n):
        convolution_sequence.add(
            tf.keras.layers.Conv3D(
                channels,
                (3, 3, 1),
                strides=1,
                padding="same",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )
        convolution_sequence.add(
            tf.keras.layers.Conv3D(
                channels,
                (1, 1, 3),
                strides=1,
                padding="valid",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )

        if i != n - 1:
            convolution_sequence.add(tf.keras.layers.ReLU())

    short_circuit_sequence = tf.keras.Sequential(name=f"down-short-circuit-d{depth}")
    short_circuit_sequence.add(tf.keras.layers.Cropping3D((0, 0, n)))
    short_circuit_sequence.add(
        tf.keras.layers.Conv3D(
            channels,
            (1, 1, 1),
            strides=1,
            padding="same",
            kernel_initializer=tf.ones_initializer(),
            use_bias=False,
        )
    )

    x = tf.keras.layers.Add()([convolution_sequence(x), short_circuit_sequence(x)])

    unet_short_circuit = x

    if pool != 0:
        x = tf.keras.layers.AveragePooling3D(
            (pool, pool, 1), strides=None, padding="valid"
        )(x)

    return x, unet_short_circuit


def fully_connected_block(x, input_size, internal_channels, output_channels):
    x = tf.keras.layers.Conv3D(
        internal_channels,
        (input_size, input_size, 1),
        strides=1,
        padding="valid",
        kernel_initializer=initializer,
        use_bias=True,
    )(x)

    repeats = 2
    for _ in range(repeats):
        short_circuit = x
        x = tf.keras.layers.ReLU()(x)
        x = tf.keras.layers.Dense(internal_channels)(x)
        x = tf.keras.layers.Add()([x, short_circuit])

    x = tf.keras.layers.ReLU()(x)
    x = tf.keras.layers.Dense(input_size * input_size * output_channels)(x)

    x = tf.keras.layers.Reshape((input_size, input_size, 1, output_channels))(x)

    return x


def up_block(x, unet_short_circuit, depth, cropping, m, channels, up_scale):
    unet_short_circuit = tf.keras.layers.Cropping3D((0, 0, cropping))(
        unet_short_circuit
    )

    if up_scale != 0:
        x = tf.keras.layers.UpSampling3D(size=(up_scale, up_scale, 1))(x)

    x = tf.keras.layers.Concatenate(axis=-2)([x, unet_short_circuit])

    convolution_sequence = tf.keras.Sequential(name=f"up-convolution-d{depth}")
    convolution_sequence.add(tf.keras.layers.ReLU())
    for _ in range(m):
        convolution_sequence.add(
            tf.keras.layers.Conv3D(
                channels,
                (3, 3, 1),
                strides=1,
                padding="same",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )
        convolution_sequence.add(tf.keras.layers.ReLU())

    internal_short_circuit = tf.keras.Sequential(name=f"up-short-circuit-d{depth}")
    internal_short_circuit.add(
        tf.keras.layers.Conv3D(
            channels,
            (1, 1, 1),
            strides=1,
            padding="same",
            kernel_initializer=tf.ones_initializer(),
            use_bias=False,
        )
    )

    x = tf.keras.layers.Add()([convolution_sequence(x), internal_short_circuit(x)])

    return x


def Model(
    grid_size=config.GRID_SIZE,
    z_context_distance=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
):
    down_block_params = [  # Start at 512, 3
        (0, (3, 0, 32, 2)),  # 256, 3
        (1, (3, 1, 32, 2)),  # 128, 2
        (2, (3, 1, 64, 4)),  # 32, 1
        (3, (3, 1, 64, 4)),  # 8, 1
        (4, (3, 0, 128, 0)),  # 8, 0
    ]
    fully_connected_params = (8, 512, 128)
    up_block_params = [
        (4, (0, 4, 64, 0)),
        (3, (0, 4, 64, 4)),
        (2, (1, 4, 32, 4)),
        (1, (2, 4, 32, 2)),
        (0, (3, 4, 32, 2)),
    ]

    inputs = tf.keras.layers.Input(
        shape=[grid_size, grid_size, z_context_distance * 2 + 1, 1],
        batch_size=batch_size,
    )

    x = inputs

    unet_short_circuits = []
    for depth, down_block_param in down_block_params:
        m, n, channels, pool = down_block_param
        x, unet_short_circuit = down_block(x, depth, m, n, channels, pool)
        unet_short_circuits.append(unet_short_circuit)

    input_size, internal_channels, output_channels = fully_connected_params
    x = fully_connected_block(x, input_size, internal_channels, output_channels)

    unet_short_circuits = reversed(unet_short_circuits)

    for unet_shot_circuit, (depth, up_block_param) in zip(
        unet_short_circuits, up_block_params
    ):
        cropping, m, channels, up_scale = up_block_param
        x = up_block(x, unet_shot_circuit, depth, cropping, m, channels, up_scale)

    x = tf.keras.layers.Conv3D(
        1,
        (1, 1, 6),
        strides=1,
        padding="valid",
        kernel_initializer=tf.ones_initializer(),
        use_bias=False,
    )(x)

    x = tf.keras.activations.sigmoid(x)

    return tf.keras.Model(inputs=inputs, outputs=x)


# # with strategy.scope():
# model = Model()
# model.compile(optimizer='adam', loss=tf.keras.losses.MeanAbsoluteError())
