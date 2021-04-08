import tensorflow as tf

initializer = tf.random_normal_initializer(0.0, 0.02)


def down_block(x, depth, num_convs, channels, pool):
    convolution_sequence = tf.keras.Sequential(name=f"down-convolution-d{depth}")
    convolution_sequence.add(tf.keras.layers.ReLU())
    for i in range(num_convs):
        convolution_sequence.add(
            tf.keras.layers.Conv2D(
                channels,
                (3, 3),
                strides=1,
                padding="same",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )
        if i != num_convs - 1:
            convolution_sequence.add(tf.keras.layers.ReLU())

    short_circuit_sequence = tf.keras.Sequential(name=f"down-short-circuit-d{depth}")
    short_circuit_sequence.add(
        tf.keras.layers.Conv2D(
            channels,
            (1, 1),
            strides=1,
            padding="same",
            kernel_initializer=tf.ones_initializer(),
            use_bias=False,
            trainable=False,
        )
    )

    x = tf.keras.layers.Add()([convolution_sequence(x), short_circuit_sequence(x)])

    unet_short_circuit = x

    if pool != 0:
        x = tf.keras.layers.AveragePooling2D(
            (pool, pool), strides=None, padding="valid"
        )(x)

    return x, unet_short_circuit


def fully_connected_block(x, input_size, internal_channels, output_channels):
    x = tf.keras.layers.Conv2D(
        internal_channels,
        (input_size, input_size),
        strides=1,
        padding="valid",
        kernel_initializer=initializer,
        use_bias=False,
    )(x)

    repeats = 2
    for _ in range(repeats):
        short_circuit = x
        x = tf.keras.layers.ReLU()(x)
        x = tf.keras.layers.Dense(internal_channels)(x)
        x = tf.keras.layers.Add()([x, short_circuit])

    x = tf.keras.layers.ReLU()(x)
    x = tf.keras.layers.Dense(input_size * input_size * output_channels)(x)

    x = tf.keras.layers.Reshape((input_size, input_size, output_channels))(x)

    return x


def up_block(x, unet_short_circuit, depth, num_convs, channels, up_scale):
    if up_scale != 0:
        x = tf.keras.layers.UpSampling2D(size=(up_scale, up_scale))(x)

    x = tf.keras.layers.Add()([x, unet_short_circuit])

    convolution_sequence = tf.keras.Sequential(name=f"up-convolution-d{depth}")
    convolution_sequence.add(tf.keras.layers.ReLU())
    for i in range(num_convs):
        convolution_sequence.add(
            tf.keras.layers.Conv2D(
                channels,
                (3, 3),
                strides=1,
                padding="same",
                kernel_initializer=initializer,
                use_bias=False,
            )
        )
        if i != num_convs - 1:
            convolution_sequence.add(tf.keras.layers.ReLU())

    internal_short_circuit = tf.keras.Sequential(name=f"up-short-circuit-d{depth}")
    internal_short_circuit.add(
        tf.keras.layers.Conv2D(
            channels,
            (1, 1),
            strides=1,
            padding="same",
            kernel_initializer=tf.ones_initializer(),
            use_bias=False,
            trainable=False,
        )
    )

    x = tf.keras.layers.Add()([convolution_sequence(x), internal_short_circuit(x)])

    return x


def Model(grid_size=GRID_SIZE):
    down_block_params = [
        (0, (3, 12, 2)),  # BS, 1024, 1024,  3 --> BS, 512, 512, 12
        (1, (3, 12, 4)),  # BS,  512,  512, 12 --> BS, 128, 128, 12
        (2, (3, 12, 4)),  # BS,  128,  128, 12 --> BS,  32,  32, 12
        (3, (3, 12, 4)),  # BS,   32,   32, 12 --> BS,   8,   8, 12
        (4, (4, 24, 0)),  # BS,    8,    8, 12 --> BS,   8,   8, 24
    ]
    fully_connected_params = (8, 96, 24)
    up_block_params = [
        (4, (4, 12, 0)),
        (3, (4, 12, 4)),
        (2, (3, 12, 4)),
        (1, (3, 12, 4)),
        (0, (3, 2, 2)),
    ]

    inputs = tf.keras.layers.Input(shape=[grid_size, grid_size, 3], batch_size=None)
    x = inputs

    unet_short_circuits = []
    for depth, down_block_param in down_block_params:
        x, unet_short_circuit = down_block(x, depth, *down_block_param)
        unet_short_circuits.append(unet_short_circuit)

    x = fully_connected_block(x, *fully_connected_params)

    unet_short_circuits = reversed(unet_short_circuits)

    for unet_shot_circuit, (depth, up_block_param) in zip(
        unet_short_circuits, up_block_params
    ):
        x = up_block(x, unet_shot_circuit, depth, *up_block_param)

    return tf.keras.Model(inputs=inputs, outputs=x)


model = Model()
model.compile(
    optimizer="adam", loss=tf.keras.losses.MeanAbsoluteError(), metrics=["accuracy"]
)

tf.keras.utils.plot_model(model, show_shapes=True, dpi=64)
