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

"""Functions for loading up the iViewDB frame contents.

The frame database format has changed accross the iView versions. The
older iView version has a FRAME.DBF file with all of the required
information. The new iView version spreads this information out over
nested _Frame.xml files.

To support these two database formats two functions are exposed from
this module. ``dbf_frame_based_database`` and
``xml_frame_based_database``.
"""


from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st
from pymedphys._imports import xmltodict

from pymedphys._streamlit.apps.wlutz import _dbf


def dbf_frame_based_database(database_directory, refresh_cache, filtered_table):
    """

    """
    frame = _dbf.load_iview_dbf(database_directory, refresh_cache, "frame")
    with_frame = filtered_table.merge(frame, left_on="PIMG_DBID", right_on="PIMG_DBID")

    with_frame = _calculate_delta_offsets(with_frame)

    filepaths = _calc_filepath_from_frames_dbid(with_frame["FRAME_DBID"])
    with_frame["filepath"] = filepaths

    return _final_frame_column_adjustment(with_frame)


def xml_frame_based_database(database_directory, filtered_table):
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
