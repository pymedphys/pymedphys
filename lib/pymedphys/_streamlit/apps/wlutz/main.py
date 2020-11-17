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


from pymedphys._imports import plt, pylinac
from pymedphys._imports import streamlit as st

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._streamlit.apps.wlutz import _dbf, _filtering, _frames
from pymedphys._streamlit.utilities import misc
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api
from pymedphys._wlutz import reporting


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

    st.sidebar.write("## Parameters")

    width = st.sidebar.number_input("Width (mm)", 20)
    length = st.sidebar.number_input("Length (mm)", 24)
    edge_lengths = [width, length]

    bb_diameter = st.sidebar.number_input("BB Diameter (mm)", 8)
    penumbra = st.sidebar.number_input("Penumbra (mm)", 2)

    if st.button("Show Image"):
        fig, ax = plt.subplots()
        ax.imshow(read_image(resolved_path))
        st.pyplot(fig)

    algorithm_options = ["PyMedPhys", "PyLinac"]
    selected_algorithms = st.multiselect(
        "Algorithms to run", algorithm_options, algorithm_options
    )

    if st.button("Calculate"):
        raw_image = read_image(resolved_path)
        (
            x,
            y,
            image,
            field,
            pymedphys_field_centre,
            field_rotation,
        ) = _get_field_parameters(raw_image, edge_lengths, penumbra)

        field_centre, field_rotation, bb_centre, fig = _pymedphys_wlutz_calculate(
            resolved_path, bb_diameter, edge_lengths, penumbra
        )

        st.pyplot(fig)


def _get_field_parameters(raw_image, edge_lengths, penumbra):
    x, y, image = iview.iview_image_transform(raw_image)
    field = imginterp.create_interpolated_field(x, y, image)
    initial_centre = findfield.get_centre_of_mass(x, y, image)
    field_centre, field_rotation = findfield.field_centre_and_rotation_refining(
        field, edge_lengths, penumbra, initial_centre
    )

    return x, y, image, field, field_centre, field_rotation


def _pymedphys_wlutz_calculate(resolved_path, bb_diameter, edge_lengths, penumbra):
    raw_image = read_image(resolved_path)
    x, y, image, field, field_centre, field_rotation = _get_field_parameters(
        raw_image, edge_lengths, penumbra
    )

    bb_centre = findbb.optimise_bb_centre(
        field, bb_diameter, edge_lengths, penumbra, field_centre, field_rotation
    )
    fig, _ = reporting.image_analysis_figure(
        x,
        y,
        image,
        bb_centre,
        field_centre,
        field_rotation,
        bb_diameter,
        edge_lengths,
        penumbra,
    )

    return field_centre, field_rotation, bb_centre, fig


def _pylinac_wlutz_calculate(resolved_path, edge_lengths, penumbra):
    raw_image = read_image(resolved_path)
    (
        x,
        y,
        image,
        field,
        pymedphys_field_centre,
        pymedphys_field_rotation,
    ) = _get_field_parameters(raw_image, edge_lengths, penumbra)

    version_to_use = pylinac.__version__
    pylinac_results = pmp_pylinac_api.run_wlutz(
        field,
        edge_lengths,
        penumbra,
        pymedphys_field_centre,
        pymedphys_field_rotation,
        find_bb=True,
        interpolated_pixel_size=0.05,
        pylinac_versions=[version_to_use],
    )

    field_centre = pylinac_results[version_to_use]["field_centre"]
    bb_centre = pylinac_results[version_to_use]["bb_centre"]

    fig, _ = reporting.image_analysis_figure(
        x,
        y,
        image,
        bb_centre,
        field_centre,
        pymedphys_field_rotation,
        bb_diameter,
        edge_lengths,
        penumbra,
    )
