# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functions for loading up the iViewDB frame database contents.

The frame database format has changed accross the iView versions. The
older iView version has a FRAME.DBF file with all of the required
information. The new iView version spreads this information out over
nested _Frame.xml files.

To support these two database formats two functions are exposed from
this module. ``dbf_frame_based_database`` and
``xml_frame_based_database``.
"""

import pathlib

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import xmltodict

from . import _dbf


def dbf_frame_based_database(
    database_directory: pathlib.Path,
    refresh_cache: bool,
    filtered_table: "pd.DataFrame",
):
    """Determine the filepaths and delivery times for each frame
    relevant to the user for a dbf based frame database.

    This is achieved by loading up the FRAME.DBF database and
    determining filename from the DBID column and delivery time by
    adjusting the image series datetime data by the DELTA_MS column.

    Parameters
    ----------
    database_directory
        The path to the iViewDB directory.
    refresh_cache
        Whether or not to reload the database caches from disk.
    filtered_table
        A filtered ``pd.DataFrame`` containing the image sequences
        relevant to the user. The column ``PIMG_DBID`` is used within
        this table to merge with the loaded FRAME database.

    Returns
    -------
    table
        A ``pandas.DataFrame`` that contains the columns "filepath",
        "time", "machine_id", "patient_id", "treatment", "port",
        "datetime", and "PIMG_DBID"

        filepath : str
            The filepath of the jpg image. Defined relative to the
            iView database directory.
        time : datetime.time
            The time of the image frame. Defined as the sum of the
            IMG_TIME column within the PATIMG database and the DELTA_MS
            column within the FRAME database. Although this information
            is available within the datetime column, this is provided
            so that the table is more informative to the user within
            the streamlit display.
        machine_id : str
            A machine identifier as defined by ORG_DTL within the
            PATIMG database.
        patient_id : str
            A patient identifier as defined by the ID column within the
            PATIENT database.
        treatment : str
            The treatment identifier as defined by the ID column within
            the TRTMNT database.
        port : str
            A port identifier as defined by the ID column within the
            PORT database.
        datetime : datetime.datetime
            The datetime representation of the image sequence start.
            Converted from the combination of the DELTA_MS columns
            within the FRAME database and the IMG_DATE and IMG_TIME
            columns within the PATIMG database.
        PIMG_DBID : int
            The DBID column from the PATIMG database.

    Notes
    -----
    If this has been run before for this given path, and
    ``refresh_cache=False``, the cached result
    for each database will be provided. The cache can be reset from the
    DBF files by passing ``refresh_cache=True``.

    """
    frame = _dbf.load_iview_dbf(database_directory, refresh_cache, "frame")
    with_frame = filtered_table.merge(frame, left_on="PIMG_DBID", right_on="PIMG_DBID")

    with_frame = _calculate_delta_offsets(with_frame)

    filepaths = _calc_filepath_from_frames_dbid(with_frame["FRAME_DBID"])
    with_frame["filepath"] = filepaths

    return _final_frame_column_adjustment(with_frame)


def xml_frame_based_database(
    database_directory: pathlib.Path, filtered_table: "pd.DataFrame"
):
    """Determine the filepaths and delivery times for each frame
    relevant to the user for an xml based frame database.

    This is achieved by loading the ``_Frame.xml`` files for each
    image series relevant to the user. The filepath is determined from
    a combination of patient_id, DICOM_UID with the ``Seq`` key found
    within the ``_Frame.xml`` file. The delivery time is determined by
    adjusting the image series datetime by the ``DeltaMs`` parameter
    found within the ``_Frame.xml`` file.

    Parameters
    ----------
    database_directory
        The path to the iViewDB directory.
    filtered_table
        A filtered ``pd.DataFrame`` containing the image sequences
        relevant to the user. The column ``DICOM_UID`` is used within
        this table to merge with the data loaded from the ``_Frame.xml``
        files.

    Returns
    -------
    table
        A ``pandas.DataFrame`` that contains the columns "filepath",
        "time", "machine_id", "patient_id", "treatment", "port",
        "datetime", and "PIMG_DBID"

        filepath : str
            The filepath of the jpg image. Defined relative to the
            iView database directory.
        time : datetime.time
            The time of the image frame. Defined as the sum of the
            IMG_TIME column within the PATIMG database and the DeltaMs
            parameter within the corresponding ``_Frame.xml`` file.
            Although this information
            is available within the datetime column, this is provided
            so that the table is more informative to the user within
            the streamlit display.
        machine_id : str
            A machine identifier as defined by ORG_DTL within the
            PATIMG database.
        patient_id : str
            A patient identifier as defined by the ID column within the
            PATIENT database.
        treatment : str
            The treatment identifier as defined by the ID column within
            the TRTMNT database.
        port : str
            A port identifier as defined by the ID column within the
            PORT database.
        datetime : datetime.datetime
            The datetime representation of the image sequence start.
            Converted from the combination of the DeltaMs
            parameter within the corresponding ``_Frame.xml`` file and
            the IMG_DATE and IMG_TIME columns within the PATIMG
            database.
        PIMG_DBID : int
            The DBID column from the PATIMG database.

    """
    xml_filepaths = _calc_xml_filepaths(filtered_table)

    xml_docs = [
        _load_xml(database_directory.joinpath(filepath)) for filepath in xml_filepaths
    ]
    frame_table_rows = []
    for doc in xml_docs:
        frame_table_rows += _data_from_doc(doc)

    frame_table = pd.DataFrame.from_dict(frame_table_rows)

    merged = filtered_table.merge(
        frame_table, left_on="DICOM_UID", right_on="DICOM_UID"
    )

    merged = _calculate_delta_offsets(merged)

    filepaths = _calc_xml_based_jpg_filepaths(merged)
    merged["filepath"] = filepaths

    return _final_frame_column_adjustment(merged)


@st.cache()
def _calc_filepath_from_frames_dbid(dbid_series):
    return [f"img/{f'{dbid:0>8x}'.upper()}.jpg" for dbid in dbid_series]


def _calculate_delta_offsets(table):
    delta = pd.to_timedelta(table["DELTA_MS"].astype(int), unit="ms")
    timestamps = table["datetime"] + delta

    table["time"] = timestamps.dt.time
    table["datetime"] = timestamps

    table.sort_values("datetime", ascending=False, inplace=True)

    return table


def _final_frame_column_adjustment(table):
    return table[
        [
            "filepath",
            "time",
            "machine_id",
            "patient_id",
            "treatment",
            "port",
            "datetime",
            "PIMG_DBID",
            "LAST_NAME",
            "FIRST_NAME",
        ]
    ]


@st.cache()
def _load_xml(filepath):
    with open(filepath) as fd:
        doc = xmltodict.parse(fd.read())

    return doc


@st.cache()
def _data_from_doc(doc):
    table_rows = []

    projection_set = doc["ProjectionSet"]
    dicom_uid = projection_set["Image"]["DicomUID"]

    frames = projection_set["Frames"]["Frame"]

    if isinstance(frames, dict):
        sequence = frames["Seq"]
        delta_ms = frames["DeltaMs"]

        table_rows.append(
            {"sequence": sequence, "DELTA_MS": delta_ms, "DICOM_UID": dicom_uid}
        )
    elif isinstance(frames, list):
        for frame in frames:
            sequence = frame["Seq"]
            delta_ms = frame["DeltaMs"]

            table_rows.append(
                {"sequence": sequence, "DELTA_MS": delta_ms, "DICOM_UID": dicom_uid}
            )
    else:
        raise ValueError("Unexpected type of frame")

    return table_rows


@st.cache()
def _calc_xml_filepaths(table):
    return (
        "patient_"
        + table["patient_id"].astype("str")
        + "/MV_IMAGES/img_"
        + table["DICOM_UID"].astype("str")
        + "/_Frame.xml"
    )


@st.cache()
def _calc_xml_based_jpg_filepaths(table):
    return (
        "patient_"
        + table["patient_id"].astype("str")
        + "/MV_IMAGES/img_"
        + table["DICOM_UID"].astype("str")
        + "/"
        + table["sequence"].str.zfill(5)
        + "."
        + table["DICOM_UID"].astype("str")
        + ".jpg"
    )
