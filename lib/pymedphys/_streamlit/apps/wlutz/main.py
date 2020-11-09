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


# import os

import datetime

# from pymedphys._imports import plt
from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg

# from pymedphys._wlutz import findbb, findfield, imginterp, iview, reporting
from pymedphys._streamlit.utilities import misc
from pymedphys._streamlit.apps.wlutz import _dbf, _filtering


@st.cache()
def read_image(path):
    return lljpeg.imread(path)


@st.cache()
def calc_filepath_from_frames_dbid(dbid_series):
    return [f"img/{f'{dbid:0>8x}'.upper()}.jpg" for dbid in dbid_series]


@st.cache()
def calc_timestamps(frame_with_filepath, patimg):
    img_date_time = patimg[["DBID", "IMG_DATE", "IMG_TIME", "PORT_DBID", "ORG_DTL"]]

    merged = frame_with_filepath.merge(
        img_date_time, left_on="PIMG_DBID", right_on="DBID"
    )[["filepath", "IMG_DATE", "IMG_TIME", "DELTA_MS", "PORT_DBID", "ORG_DTL"]]

    resolved = pd.DataFrame()
    resolved["filepath"] = merged["filepath"]
    timestamps_string = (
        merged["IMG_DATE"].astype("str")
        + "T"
        + merged["IMG_TIME"].astype("str")
        + "000"
    )

    timestamps = pd.to_datetime(timestamps_string, format="%Y%m%dT%H%M%S%f")
    delta = pd.to_timedelta(merged["DELTA_MS"], unit="ms")

    timestamps = timestamps + delta

    resolved["timestamps_string"] = timestamps_string
    resolved["delta"] = delta
    resolved["delta_seconds"] = delta.dt.total_seconds()
    resolved["date"] = timestamps.dt.date
    resolved["time"] = timestamps.dt.time
    resolved["datetime"] = timestamps
    resolved["PORT_DBID"] = merged["PORT_DBID"]
    resolved["machine_id"] = merged["ORG_DTL"]

    resolved.sort_values("datetime", inplace=True, ascending=False)

    return resolved


def main():
    st.title("Winston-Lutz Arc")

    _, database_directory = misc.get_site_and_directory("Database Site", "iviewdb")

    st.write("## Load databases for a given date")
    refresh_cache = st.button("Re-query database")
    merged = _dbf.loading_and_merging_dbfs(database_directory, refresh_cache)

    st.write("## Filtering")
    filtered = _filtering.filtering_image_sets(merged)

    st.write(filtered)

    # st.write(merged)

    # port = load_dbf(database_directory, refresh_cache, "port")

    # merged_with_port = patimg_filtered_by_date.merge(
    #     port, left_on="PORT_DBID", right_on="PORT_DBID"
    # )
    # st.write(merged_with_port)

    try:
        frames = dbf_to_pandas(frame_dbf_path, refresh_cache)
    except FileNotFoundError:
        st.write(
            ValueError(
                "Currently only iView DB formats that include FRAME.dbf are supported"
            )
        )
        st.stop()

    filepaths = calc_filepath_from_frames_dbid(frames["DBID"])

    frame_with_filepath = frames[["DBID", "PIMG_DBID", "DELTA_MS"]]
    frame_with_filepath["filepath"] = filepaths

    timestamps = calc_timestamps(frame_with_filepath, patimg)

    date_options = timestamps["date"].unique()

    selected_date = st.selectbox("Date", options=date_options)
    table_matching_selected_date = timestamps.loc[timestamps["date"] == selected_date]

    port_dbf_path = database_directory.joinpath("PORT.dbf")
    port = dbf_to_pandas(port_dbf_path, refresh_cache)[["DBID", "ID", "TRT_DBID"]]

    with_port_id = table_matching_selected_date.merge(
        port, left_on="PORT_DBID", right_on="DBID"
    )[["machine_id", "filepath", "time", "ID", "TRT_DBID", "datetime"]]

    with_port_id.rename({"ID": "port"}, axis="columns", inplace=True)

    trtmnt_dbf_path = database_directory.joinpath("TRTMNT.dbf")
    trtmnt = dbf_to_pandas(trtmnt_dbf_path, refresh_cache)[["DBID", "ID", "PAT_DBID"]]

    with_trtmnt = with_port_id.merge(trtmnt, left_on="TRT_DBID", right_on="DBID")[
        ["machine_id", "filepath", "time", "ID", "port", "PAT_DBID", "datetime"]
    ]
    with_trtmnt.rename({"ID": "treatment"}, axis="columns", inplace=True)

    patient_dbf_path = database_directory.joinpath("PATIENT.dbf")
    patient = dbf_to_pandas(patient_dbf_path, refresh_cache)[
        ["DBID", "ID", "LAST_NAME", "FIRST_NAME"]
    ]

    with_patient = with_trtmnt.merge(patient, left_on="PAT_DBID", right_on="DBID")[
        [
            "machine_id",
            "ID",
            "time",
            "treatment",
            "port",
            "filepath",
            "LAST_NAME",
            "FIRST_NAME",
            "datetime",
        ]
    ]

    with_patient.rename(
        {"ID": "patient_id", "LAST_NAME": "last_name", "FIRST_NAME": "first_name"},
        axis="columns",
        inplace=True,
    )

    st.write(with_patient)

    # table_matching_selected_date.merge()

    # files = get_jpg_list(database_directory)

    # # st.write(files)
    # sorted_files = sorted(files, key=get_modified_time, reverse=True)
    # image_path = st.selectbox("Image to select", options=sorted_files[0:10])

    # st.write("## Parameters")

    # width = st.number_input("Width (mm)", 20)
    # length = st.number_input("Length (mm)", 24)
    # edge_lengths = [width, length]

    # # initial_rotation = 0
    # bb_diameter = st.number_input("BB Diameter (mm)", 8)
    # penumbra = st.number_input("Penumbra (mm)", 2)

    # # files = sorted(IMAGES_DIR.glob("*.jpg"), key=lambda t: -os.stat(t).st_mtime)
    # # most_recent = files[0:5]

    # # most_recent

    # if st.button("Show Image"):
    #     fig = plt.figure()
    #     fig.imshow(read_image(image_path))
    #     st.pyplot(fig)

    # if st.button("Calculate"):
    #     img = read_image(image_path)
    #     x, y, img = iview.iview_image_transform(img)
    #     field = imginterp.create_interpolated_field(x, y, img)
    #     initial_centre = findfield.get_centre_of_mass(x, y, img)
    #     (field_centre, field_rotation) = findfield.field_centre_and_rotation_refining(
    #         field, edge_lengths, penumbra, initial_centre, fixed_rotation=0
    #     )

    #     bb_centre = findbb.optimise_bb_centre(
    #         field, bb_diameter, edge_lengths, penumbra, field_centre, field_rotation
    #     )
    #     fig = reporting.image_analysis_figure(
    #         x,
    #         y,
    #         img,
    #         bb_centre,
    #         field_centre,
    #         field_rotation,
    #         bb_diameter,
    #         edge_lengths,
    #         penumbra,
    #     )

    #     st.write(fig)
    #     st.pyplot()
