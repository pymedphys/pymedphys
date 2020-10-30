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


# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import os
import pathlib

import matplotlib.pyplot as plt

import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit import rerun as st_rerun
from pymedphys._wlutz import findbb, findfield, imginterp, iview, reporting

st_rerun.autoreload([st_rerun])


st.title("Winston Lutz Arc")

DATAEXCHANGE_DIRECTORY = pathlib.Path(r"S:\DataExchange")
IVIEW_DB = DATAEXCHANGE_DIRECTORY.joinpath("iViewDB")
IMAGES_DIR = IVIEW_DB.joinpath("img")

"## Parameters"

number_of_images = st.number_input("Number of Images", 10)

width = st.number_input("Width (mm)", 20)
length = st.number_input("Length (mm)", 24)
edge_lengths = [width, length]

initial_rotation = 0
bb_diameter = st.number_input("BB Diameter (mm)", 8)
penumbra = st.number_input("Penumbra (mm)", 2)

# files = sorted(IMAGES_DIR.glob("*.jpg"), key=lambda t: -os.stat(t).st_mtime)
# most_recent = files[0:5]

# most_recent


@st.cache()
def get_file_list():
    return tuple([str(path) for path in IMAGES_DIR.glob("*.jpg")])


files = get_file_list()
most_recent = sorted(files, key=lambda t: -os.stat(t).st_mtime)[0:number_of_images]

image_path = st.radio("Image to select", options=most_recent)


@st.cache()
def read_image(path):
    return lljpeg.imread(path)


plt.imshow(read_image(image_path))
st.pyplot()

if st.button("Calculate"):
    img = read_image(image_path)
    x, y, img = iview.iview_image_transform(img)
    field = imginterp.create_interpolated_field(x, y, img)
    initial_centre = findfield.get_centre_of_mass(x, y, img)
    (field_centre, field_rotation) = findfield.field_centre_and_rotation_refining(
        field, edge_lengths, penumbra, initial_centre, fixed_rotation=0
    )

    bb_centre = findbb.optimise_bb_centre(
        field, bb_diameter, edge_lengths, penumbra, field_centre, field_rotation
    )
    fig = reporting.image_analysis_figure(
        x,
        y,
        img,
        bb_centre,
        field_centre,
        field_rotation,
        bb_diameter,
        edge_lengths,
        penumbra,
    )

    st.write(fig)
    st.pyplot()
