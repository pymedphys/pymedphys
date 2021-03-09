# Copyright (C) 2021 Derek Lane, Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Uses Mosaiq SQL to extract patient sessions and offsets.
"""

from datetime import datetime, timedelta
from typing import Iterator, List, Optional, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import sklearn

from . import api
from .connect import Connection


def cluster_sessions(
    tx_datetimes: List[datetime], interval=timedelta(hours=3)
) -> Iterator[Tuple[int, datetime, datetime]]:
    """Clusters a list of datetime objects representing tx beam delivery times

    Uses the scikit-learn hierarchical clustering algorithm
    (AgglomerativeClustering) to cluster the dose_hst datetimes

    Parameters
    ----------
    tx_datetimes : list[datetime]
        A list of datetime objects corresponding to each dose recording
        (i.e. Dose_Hst.Tx_DtTm in the Mosaiq db)
        ** The list is assumed to be sorted in increasing date/time order

    interval : timedelta
        the minimum interval between tx_datetimes to include in the
        same cluster

    Returns
    -------
    generated sequence of tuples:
        * session number, starting at 1 and incrementing
        * start_session: datetime when the session starts
        * end_session: datetime when the session ends

    Examples
    --------
    >>> from datetime import datetime, timedelta
    >>> test_datetimes = [datetime(2019, 12, 19) + timedelta(hours=h*5 + j) for h in range(3) for j in range(3)]
    >>> list(cluster_sessions(test_datetimes))     #doctest: +NORMALIZE_WHITESPACE
    [(1,
    datetime.datetime(2019, 12, 19, 0, 0),
    datetime.datetime(2019, 12, 19, 2, 0)),
    (2,
    datetime.datetime(2019, 12, 19, 5, 0),
    datetime.datetime(2019, 12, 19, 7, 0)),
    (3,
    datetime.datetime(2019, 12, 19, 10, 0),
    datetime.datetime(2019, 12, 19, 12, 0))]
    """
    # turn the datetimes in to timestamps (seconds in the epoch)
    timestamps = [[tx_datetime.timestamp()] for tx_datetime in tx_datetimes]

    # set up the cluster algorithm
    cluster_algo = sklearn.cluster.AgglomerativeClustering(
        n_clusters=None, distance_threshold=interval.seconds, linkage="single"
    )

    # and fit the timestamps to clusters
    labels = cluster_algo.fit_predict(timestamps)

    # the resulting labels are arbitrary, so iterate and collect
    #   all of the datetimes for each label
    current_label, current_session_number = labels[0], 1
    start_session = datetime.fromtimestamp(timestamps[0][0])
    end_session = start_session

    # now iterate through the labels and timestamps,
    #   extracting each session
    for label, timestamp in zip(labels, timestamps):
        if label != current_label:
            # we have a new label, so yield the current session
            yield (current_session_number, start_session, end_session)

            # and update session stats for the next one
            current_session_number += 1
            current_label = label
            start_session = datetime.fromtimestamp(timestamp[0])
            end_session = start_session
        else:
            # if the same label, then just update the end_session
            #   for the new timestamp
            end_session = datetime.fromtimestamp(timestamp[0])

    # yield the final session
    yield (current_session_number, start_session, end_session)


def sessions_for_site(
    connection: Connection, sit_set_id: int
) -> Iterator[Tuple[int, datetime, datetime]]:
    """Determines the sessions for the given site (by SIT_SET_ID)

    uses cluster_sessions after querying for the Dose_Hst.Tx_DtTm
    that are associated to the site

    Parameters
    ----------
    connection : pymssql connection opened with pymedphys.mosaiq.connect

    sit_set_id : int
        the SIT_SET_ID for the site of interest

    Returns
    -------
    generated sequence of session tuples
        same format as returned by cluster_sessions
    """
    result = api.execute(
        connection,
        """
        SELECT
            Tx_DtTm
        FROM Dose_Hst
        INNER JOIN
            Site ON Site.SIT_ID = Dose_Hst.SIT_ID
        WHERE
            Site.SIT_SET_ID = %(sit_set_id)s
        ORDER BY Dose_Hst.Tx_DtTm
        """,
        {"sit_set_id": sit_set_id},
    )

    # cluster_sessions expects a sorted list, so extract
    #   the Tx_DtTm value from each row
    dose_hst_datetimes = [row[0] for row in result]
    assert isinstance(dose_hst_datetimes[0], datetime)
    return cluster_sessions(dose_hst_datetimes)


def session_offsets_for_site(
    connection: Connection, sit_set_id: int, interval=timedelta(hours=1)
) -> Iterator[Tuple[int, Optional["np.ndarray"]]]:
    """extract the session offsets (one offset per session ) for the given site

    Parameters
    ----------
    connection : pymssql connection opened with pymedphys.mosaiq.connect

    sit_set_id : int
        the SIT_SET_ID for the site of interest

    interval : timedelta
        the interval before the session to look for the offset
        (Offset.Study_DtTm can precede the Dose_Hst records
        for the session)

    Returns
    -------
    generated sequence of tuples:
        * session_num = session number, as returned by sessions_for_site
        * Offset translation as an np.ndarray, or
                None if no offsets were found for the session
    """
    for session_num, start_session, end_session in sessions_for_site(
        connection, sit_set_id
    ):

        # calculate the time window within which the offset may occur
        window_start, window_end = (start_session - interval, end_session)

        # query for offsets within the time window
        offsets = api.execute(
            connection,
            """
            SELECT
                Study_DtTm,
                Superior_Offset,
                Anterior_Offset,
                Lateral_Offset
            FROM Offset
            WHERE
                Version = 0
                AND Offset.Offset_State IN (1,2) -- active/complete offsets
                AND Offset.Offset_Type IN (3,4) -- Portal/ThirdParty offsets
                AND Offset.SIT_SET_ID = %(sit_set_id)s
                AND %(window_start)s < Offset.Study_DtTm
                AND Offset.Study_DtTm < %(window_end)s
            ORDER BY Study_DtTm
            """,
            {
                "sit_set_id": sit_set_id,
                "window_start": window_start.strftime("%Y-%m-%d %H:%M"),
                "window_end": window_end.strftime("%Y-%m-%d %H:%M"),
            },
        )

        # just take the first offset, for now
        # more sophisticated logic is in order (i.e. is it associated with
        #       an approved image?)
        offsets = list(offsets)
        if offsets:
            yield (
                session_num,
                np.array(offsets[0][1:4]),
            )
        else:
            yield (session_num, None)


def mean_session_offset_for_site(
    connection: Connection, sit_set_id: int
) -> Optional["np.ndarray"]:
    """computes the mean session offset for the site

    Parameters
    ----------
    connection : Connection
        an open connection object to be used for queries
    sit_set_id : int
        the sit_sit_id for the site of interest

    Returns
    -------
    Optional[np.ndarray]
        mean of the session offset translation component for the site,
        or None if there are no session offsets
    """
    offsets = []
    for _, offset in session_offsets_for_site(connection, sit_set_id):
        if np.any(offset):
            offsets.append(offset)

    if offsets:
        return np.mean(offsets, 0)

    return None


def localization_offset_for_site(
    connection: Connection, sit_set_id: int
) -> Optional["np.ndarray"]:
    """get the localization offset for the given site

    Parameters
    ----------
    connection : Connection
        an open connection object to be used for queries
    sit_set_id : int
        the sit_sit_id for the site of interest

    Returns
    -------
    Optional[np.ndarray]
        most recent localization offset translation, if one is found
    """
    offsets = api.execute(
        connection,
        """
            SELECT
                Superior_Offset,
                Anterior_Offset,
                Lateral_Offset
            FROM Offset
            WHERE
                Version = 0
                AND Offset.Offset_State IN (1,2) -- active/complete offsets
                AND Offset.Offset_Type IN (2) -- localization offsets
                AND Offset.SIT_SET_ID = %(sit_set_id)s
            ORDER BY
                Offset.Study_DtTm DESC
        """,
        {"sit_set_id": sit_set_id},
    )

    offsets = list(offsets)
    if len(offsets) > 0:
        return np.array(offsets[0])

    # no localization offsets
    return None
