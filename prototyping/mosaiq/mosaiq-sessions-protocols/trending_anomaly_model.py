import numpy as np
import tensorflow as tf
from sklearn.cluster import AgglomerativeClustering
from pymedphys.mosaiq import connect
from datetime import datetime, timedelta
from pprint import pprint


def cluster_sessions(tx_dttms, interval=timedelta(hours=3)):
    """
    for a sorted list of date/time stamps, form clusters corresponding to sessions
    """
    timestamps = [[tx_dttm.timestamp()] for tx_dttm in tx_dttms]
    clusterer = AgglomerativeClustering(
        n_clusters=None, distance_threshold=interval.seconds
    )
    labels = clusterer.fit_predict(timestamps)
    current_session_number, current_label = labels[0], 1
    start_session = datetime.fromtimestamp(timestamps[0][0])
    end_session = start_session
    for label, timestamp in zip(labels, timestamps):
        if label != current_label:
            yield (current_session_number, start_session, end_session)
            current_session_number += 1
            current_label = label
            start_session = datetime.fromtimestamp(timestamp[0])
            end_session = start_session
        else:
            end_session = datetime.fromtimestamp(timestamp[0])
    yield (current_session_number, start_session, end_session)


def sessions_for_site(sit_set_id):
    """
    for a sorted list of date/time stamps, form clusters corresponding to sessions
    """
    with connect(".") as cursor:
        cursor.execute(
            "SELECT Tx_DtTm FROM Dose_Hst "
            "INNER JOIN Site ON Site.SIT_ID = Dose_Hst.SIT_ID "
            "WHERE Site.SIT_SET_ID = %s "
            "ORDER BY Dose_Hst.Tx_DtTm",
            sit_set_id,
        )
        dose_hst_dttms = [rec[0] for rec in cursor]
        return cluster_sessions(dose_hst_dttms)


def session_offsets_for_site(sit_set_id):
    """
    for a sorted list of date/time stamps, form clusters corresponding to sessions
    """
    session_offsets = {}
    for session in sessions_for_site(sit_set_id):
        with connect(".") as cursor:
            start_time_str = (session[1] - timedelta(hours=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            end_time_str = (session[2] + timedelta(hours=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            cursor.execute(
                "SELECT Superior_Offset, Anterior_Offset, Lateral_Offset FROM Offset "
                "WHERE %s < Offset.Study_DtTm "
                "AND Offset.Study_DtTm < %s "
                "ORDER BY Offset.Study_DtTm",
                (start_time_str, end_time_str),
            )

            session_offsets[session[0]] = list(cursor)

    return session_offsets


def localization_offset_for_site(sit_set_id):
    """"""
    with connect(".") as cursor:
        cursor.execute(
            "SELECT Superior_Offset, Anterior_Offset, Lateral_Offset FROM Offset "
            "WHERE %s < Offset.Study_DtTm "
            "AND Offset.Study_DtTm < %s "
            "ORDER BY Offset.Study_DtTm",
            (start_time_str, end_time_str),
        )

        localization_offset = list(cursor)[0]
        test_offset = np.array([0.0, 0.0, 0.0])

        # determine session for localization offset
        return 0, localization_offset


def generate_trending_anomaly_dataset(balance_classes=True):
    with connect(".") as cursor:
        cursor.execute("SELECT SIT_SET_ID FROM Site WHERE Version = 0")
        for sit_set_id in cursor:
            offsets_by_session = session_offsets_for_site(sit_set_id)
            # does it have a trending session?
            no_offset_sessions = [
                kvp[0] for kvp in offsets_by_session.items() if len(kvp[1]) == 0
            ]

            if len(offsets_by_session) < 5 or len(no_offset_sessions) < 2:
                # skip
                continue

            mean_session_offset = np.mean(offsets, 0)
            is_anomaly = 0.0
            yield (offsets, is_anomaly)


def train_trending_anomaly_model(save=True):
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

    ds = generate_trending_anomaly_dataset()
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
