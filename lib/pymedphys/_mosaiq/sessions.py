# Copyright (C) 2026 Derek Lane
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


"""Uses Mosaiq SQL to extract patient sessions and offsets."""

from datetime import datetime, timedelta
from typing import Iterable, Iterator, Optional, Tuple

from pymedphys._imports import numpy as np

from . import api
from .connect import Connection

# Mosaiq's default treatment session interval (Config.Tx_Interval_Time),
# used when no department setting applies
DEFAULT_SESSION_INTERVAL = timedelta(hours=3)


def cluster_sessions(
    tx_datetimes: Iterable[datetime],
    interval: timedelta = DEFAULT_SESSION_INTERVAL,
    split_on_date: bool = True,
) -> Iterator[Tuple[int, datetime, datetime]]:
    """Groups tx beam delivery times into sessions, as Mosaiq numbers them

    A treatment starts a new session when it is more than ``interval``
    after the first treatment of the current session, or (when
    ``split_on_date`` is set) when it falls on a different date from that
    first treatment. A treatment exactly ``interval`` after the first one
    stays in the same session, so no session lasts longer than ``interval``.

    Parameters
    ----------
    tx_datetimes : iterable of datetime
        datetime objects corresponding to each dose recording
        (i.e. Dose_Hst.Tx_DtTm in the Mosaiq db)
        ** assumed to be sorted in increasing date/time order

    interval : timedelta
        the longest time from the first treatment of a session to any
        other treatment in it (Mosaiq's treatment session interval,
        Config.Tx_Interval_Time)

    split_on_date : bool
        whether a change of date always starts a new session, so that
        sessions never cross midnight

    Returns
    -------
    generated sequence of tuples:
        * session number, starting at 1 and incrementing
        * start_session: datetime when the session starts
        * end_session: datetime when the session ends

    An empty input gives no sessions, and a single treatment gives one.

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

    Sessions are measured from their first treatment, so hourly
    treatments do not chain into one long session:

    >>> hourly = [datetime(2019, 12, 19) + timedelta(hours=h) for h in range(6)]
    >>> [(n, start.hour, end.hour) for n, start, end in cluster_sessions(hourly)]
    [(1, 0, 3), (2, 4, 5)]
    """
    session_number = 0
    start_session: Optional[datetime] = None
    end_session: Optional[datetime] = None

    for tx_datetime in tx_datetimes:
        if (
            start_session is None
            or tx_datetime - start_session > interval
            or (split_on_date and tx_datetime.date() != start_session.date())
        ):
            if start_session is not None and end_session is not None:
                yield (session_number, start_session, end_session)

            session_number += 1
            start_session = tx_datetime

        end_session = tx_datetime

    if start_session is not None and end_session is not None:
        yield (session_number, start_session, end_session)


def session_interval_for_site(connection: Connection, sit_set_id: int) -> timedelta:
    """Gets the treatment session interval for the site's department

    Looks up Config.Tx_Interval_Time (stored in hundredths of a second) for
    the departments (Dose_Hst.Inst_ID) that recorded the site's treatments.
    As in sessions_for_site, QA-mode deliveries and deliveries without a
    treatment time are excluded.

    Parameters
    ----------
    connection : pymssql connection opened with pymedphys.mosaiq.connect

    sit_set_id : int
        the SIT_SET_ID for the site of interest

    Returns
    -------
    timedelta
        the department's session interval, or DEFAULT_SESSION_INTERVAL
        (3 hours) when the site has no treatments with a department setting

    Raises
    ------
    ValueError
        if the site's treatments were recorded by departments with
        different session intervals; pass ``interval`` explicitly then
    """
    result = api.execute(
        connection,
        """
        SELECT DISTINCT
            Config.Tx_Interval_Time
        FROM Dose_Hst
        INNER JOIN
            Site ON Site.SIT_ID = Dose_Hst.SIT_ID
        INNER JOIN
            Config ON Config.Inst_ID = Dose_Hst.Inst_ID
        WHERE
            Site.SIT_SET_ID = %(sit_set_id)s
            AND Dose_Hst.WasQAMode = 0
            AND Dose_Hst.Tx_DtTm IS NOT NULL
        """,
        {"sit_set_id": sit_set_id},
    )

    intervals = sorted(
        timedelta(seconds=row[0] / 100) for row in result if row[0] is not None
    )
    if not intervals:
        return DEFAULT_SESSION_INTERVAL

    if len(intervals) > 1:
        raise ValueError(
            f"The treatments for SIT_SET_ID {sit_set_id} were recorded by "
            "departments with different treatment session intervals "
            f"({', '.join(str(i) for i in intervals)}). "
            "Pass the interval to use explicitly."
        )

    return intervals[0]


def sessions_for_site(
    connection: Connection, sit_set_id: int, interval: Optional[timedelta] = None
) -> Iterator[Tuple[int, datetime, datetime]]:
    """Determines the sessions for the given site (by SIT_SET_ID)

    uses cluster_sessions after querying for the Dose_Hst.Tx_DtTm
    that are associated to the site. Treatments recorded in QA mode
    (Dose_Hst.WasQAMode) are excluded, as Mosaiq numbers them separately.

    Session numbers count the site's sessions only, so they differ from the
    Treatment Chart's per-patient numbers when several of a patient's
    sites are treated in the same visit.

    Parameters
    ----------
    connection : pymssql connection opened with pymedphys.mosaiq.connect

    sit_set_id : int
        the SIT_SET_ID for the site of interest

    interval : timedelta, optional
        the treatment session interval, as for cluster_sessions; by
        default, the department's setting from session_interval_for_site

    Returns
    -------
    generated sequence of session tuples
        same format as returned by cluster_sessions; none if the site
        has no treatments
    """
    if interval is None:
        interval = session_interval_for_site(connection, sit_set_id)

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
            AND Dose_Hst.WasQAMode = 0
            AND Dose_Hst.Tx_DtTm IS NOT NULL
        ORDER BY Dose_Hst.Tx_DtTm
        """,
        {"sit_set_id": sit_set_id},
    )

    # cluster_sessions expects a sorted list, so extract
    #   the Tx_DtTm value from each row
    dose_hst_datetimes = [row[0] for row in result]
    assert all(isinstance(tx_dttm, datetime) for tx_dttm in dose_hst_datetimes)
    return cluster_sessions(dose_hst_datetimes, interval)


def session_offsets_for_site(
    connection: Connection,
    sit_set_id: int,
    interval=timedelta(hours=1),
    session_interval: Optional[timedelta] = None,
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
        for the session); the search never reaches back past the
        previous session's last treatment

    session_interval : timedelta, optional
        the treatment session interval passed to sessions_for_site; by
        default, the department's setting

    Returns
    -------
    generated sequence of tuples:
        * session_num = session number, as returned by sessions_for_site
        * Offset translation as an np.ndarray, or
                None if no offsets were found for the session
    """
    previous_session_end: Optional[datetime] = None
    for session_num, start_session, end_session in sessions_for_site(
        connection, sit_set_id, session_interval
    ):
        # calculate the time window within which the offset may occur,
        #   starting no earlier than the end of the previous session
        window_start = start_session - interval
        if previous_session_end is not None:
            window_start = max(window_start, previous_session_end)
        window_end = end_session
        previous_session_end = end_session

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
                "window_start": window_start,
                "window_end": window_end,
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
    connection: Connection,
    sit_set_id: int,
    session_interval: Optional[timedelta] = None,
) -> Optional["np.ndarray"]:
    """computes the mean session offset for the site

    Parameters
    ----------
    connection : Connection
        an open connection object to be used for queries
    sit_set_id : int
        the sit_sit_id for the site of interest
    session_interval : Optional[timedelta]
        the treatment session interval passed to sessions_for_site; by
        default, the department's setting

    Returns
    -------
    Optional[np.ndarray]
        mean of the session offset translation component for the site,
        or None if there are no session offsets
    """
    offsets: list[np.ndarray] = []
    for _, offset in session_offsets_for_site(
        connection, sit_set_id, session_interval=session_interval
    ):
        if offset is not None and np.any(offset):
            offsets.append(offset)

    if offsets:
        result: np.ndarray = np.mean(offsets, 0)  # type: ignore[assignment]
        return result

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
