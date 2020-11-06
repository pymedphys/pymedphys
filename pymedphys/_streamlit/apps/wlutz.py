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
from pymedphys._streamlit.utilities import dbf, misc


@st.cache()
def read_image(path):
    return lljpeg.imread(path)


def dbf_to_pandas_without_cache(path):
    return pd.DataFrame(iter(dbf.get_dbf_table(path)))


@st.cache()
def dbf_to_pandas_with_cache(path):
    return [dbf_to_pandas_without_cache(path)]


def dbf_to_pandas(path, refresh_cache=False):
    result = dbf_to_pandas_with_cache(path)

    if refresh_cache:
        result[0] = dbf_to_pandas_without_cache(path)

    return result[0]


@st.cache()
def calc_filenames(dbid_series):
    return [f"{f'{dbid:0>8x}'.upper()}.jpg" for dbid in dbid_series]


@st.cache()
def calc_timestamps(frames, patimg):
    filenames = calc_filenames(frames["DBID"])

    frame_with_filename = frames[["DBID", "PIMG_DBID", "DELTA_MS"]]
    frame_with_filename["filename"] = filenames

    img_date_time = patimg[["DBID", "IMG_DATE", "IMG_TIME", "PORT_DBID", "ORG_DTL"]]

    merged = frame_with_filename.merge(
        img_date_time, left_on="PIMG_DBID", right_on="DBID"
    )[["filename", "IMG_DATE", "IMG_TIME", "DELTA_MS", "PORT_DBID", "ORG_DTL"]]

    resolved = pd.DataFrame()
    resolved["filename"] = merged["filename"]
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

    frame_dbf_path = database_directory.joinpath("FRAME.dbf")
    refresh_cache = st.button("Re-query database")

    try:
        frames = dbf_to_pandas(frame_dbf_path, refresh_cache)
    except FileNotFoundError:
        st.write(
            ValueError(
                "Currently only iView DB formats that include FRAME.dbf are supported"
            )
        )
        st.stop()

    patimg_dbf_path = database_directory.joinpath("PATIMG.dbf")
    patimg = dbf_to_pandas(patimg_dbf_path, refresh_cache)

    timestamps = calc_timestamps(frames, patimg)

    date_options = timestamps["date"].unique()

    selected_date = st.selectbox("Date", options=date_options)
    table_matching_selected_date = timestamps.loc[timestamps["date"] == selected_date]

    port_dbf_path = database_directory.joinpath("PORT.dbf")
    port = dbf_to_pandas(port_dbf_path, refresh_cache)[["DBID", "ID", "TRT_DBID"]]

    with_port_id = table_matching_selected_date.merge(
        port, left_on="PORT_DBID", right_on="DBID"
    )[["machine_id", "filename", "time", "ID", "TRT_DBID", "datetime"]]

    with_port_id.rename({"ID": "port"}, axis="columns", inplace=True)

    trtmnt_dbf_path = database_directory.joinpath("TRTMNT.dbf")
    trtmnt = dbf_to_pandas(trtmnt_dbf_path, refresh_cache)[["DBID", "ID", "PAT_DBID"]]

    with_trtmnt = with_port_id.merge(trtmnt, left_on="TRT_DBID", right_on="DBID")[
        ["machine_id", "filename", "time", "ID", "port", "PAT_DBID", "datetime"]
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
            "filename",
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

    st.write("## Filtering")

    filtering_df = with_patient

    # Machine ID
    machine_id = st.radio("Machine", filtering_df["machine_id"].unique())
    filtering_df = filtering_df.loc[filtering_df["machine_id"] == machine_id]

    # Patient ID
    patient_id = st.radio("Patient", filtering_df["patient_id"].unique())
    filtering_df = filtering_df.loc[filtering_df["patient_id"] == patient_id]

    # Time
    time_step = datetime.timedelta(minutes=1)
    min_time = (np.min(filtering_df["datetime"])).floor("min").time()
    max_time = (np.max(filtering_df["datetime"])).ceil("min").time()

    time_range = st.slider(
        "Time",
        min_value=min_time,
        max_value=max_time,
        step=time_step,
        value=[min_time, max_time],
    )

    filtering_df = filtering_df.loc[
        (filtering_df["time"] >= time_range[0])
        & (filtering_df["time"] <= time_range[1])
    ]

    # Treatments
    unique_treatments = filtering_df["treatment"].unique().tolist()
    selected_treatments = st.multiselect(
        "Treatment", unique_treatments, default=unique_treatments
    )
    filtering_df = filtering_df.loc[filtering_df["treatment"].isin(selected_treatments)]

    # Ports
    unique_ports = filtering_df["port"].unique().tolist()
    selected_ports = st.multiselect("Ports", unique_ports, default=unique_ports)
    filtering_df = filtering_df.loc[filtering_df["port"].isin(selected_ports)]

    st.write(filtering_df)

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
