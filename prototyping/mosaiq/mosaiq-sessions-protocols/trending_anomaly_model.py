from datetime import datetime, timedelta
from pprint import pprint

import numpy as np
import tensorflow as tf

from pymedphys.mosaiq import Connection, connect, execute
from pymedphys._mosaiq.sessions import (
    mean_session_offsets_for_site,
    localization_offset_for_site,
)


def generate_trending_anomaly_dataset(connection: Connection, balance_classes=True):
    """generate a tensorflow dataset for trending analysis

    Parameters
    ----------
    balance_classes : bool, optional
        [description], by default True

    Yields
    -------
    [type]
        [description]
    """
    result = execute(
        connection,
        """
        SELECT
            SIT_SET_ID
        FROM Site
        WHERE Version = 0
        """,
    )

    print(balance_classes)

    for sit_set_id in result:
        offsets_by_session = mean_session_offsets_for_site(sit_set_id)

        # does it have a trending session?
        no_offset_sessions = [
            kvp[0] for kvp in offsets_by_session.items() if len(kvp[1]) == 0
        ]

        if len(offsets_by_session) < 5 or len(no_offset_sessions) < 2:
            # skip
            continue

        mean_session_offset = np.mean(offsets_by_session, 0)
        print(mean_session_offset)
        is_anomaly = 0.0
        yield (mean_session_offset, is_anomaly)


def train_trending_anomaly_model(connection, save=True):
    """create a MLP that can be trained on

    Parameters
    ----------
    save : bool, optional
        [description], by default True

    Returns
    -------
    [type]
        [description]
    """
    # create model
    layers = [
        tf.keras.layers.Input(shape=(7,)),
        tf.keras.layers.Dense(5, activation="relu"),
        tf.keras.layers.Dense(1, activation="softmax"),
    ]
    model = tf.keras.Sequential(layers)
    model.summary()

    adam = tf.optimizers.Adam()  # lr=0.001, decay=1e-8)
    model.compile(loss="binary_crossentropy", optimizer=adam)

    ds = generate_trending_anomaly_dataset(connection)
    ds_batch = ds.batch(32)
    model.fit(ds_batch, epochs=10)
    return model


if __name__ == "__main__":
    if args == "train":
        # call training
        # write out model parameters
        pass
    elif args == "predict":
        # read model parameters
        # apply to particular site
        pass
