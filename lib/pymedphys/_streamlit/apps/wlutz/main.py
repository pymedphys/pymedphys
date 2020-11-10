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


from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit.apps.wlutz import _dbf, _filtering, _frames

# from pymedphys._wlutz import findbb, findfield, imginterp, iview, reporting
from pymedphys._streamlit.utilities import misc


@st.cache()
def read_image(path):
    return lljpeg.imread(path)


def main():
    st.title("Winston-Lutz Arc")

    _, database_directory = misc.get_site_and_directory("Database Site", "iviewdb")

    st.write("## Load iView databases for a given date")
    refresh_cache = st.button("Re-query databases")
    merged = _dbf.load_and_merge_dbfs(database_directory, refresh_cache)

    st.write("## Filtering")
    filtered = _filtering.filter_image_sets(merged)
    filtered.sort_values("datetime", ascending=False, inplace=True)

    st.write(filtered)

    if len(filtered) == 0:
        st.stop()

    st.write("## Loading database image frame data")

    try:
        table = _frames.dbf_frame_based_database(
            database_directory, refresh_cache, filtered
        )
    except FileNotFoundError:
        table = _frames.xml_frame_based_database(database_directory, filtered)

    st.write(table)

    selected_filepath = st.selectbox("Select single filepath", table["filepath"])

    resolved_path = database_directory.joinpath(selected_filepath)
    st.write(resolved_path)

    fig, ax = plt.subplots()
    ax.imshow(read_image(resolved_path))
    st.pyplot(fig)

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
