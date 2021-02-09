# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import tempfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.streamlit.utilities.dicom import loader as _loader
from pymedphys._experimental.vendor.pylinac_vendored._pylinac_installed import (
    pylinac as _pylinac_installed,
)
from pymedphys._experimental.wlutz import reporting as _reporting

CATEGORY = categories.PLANNING
TITLE = "DICOM WLutz"


def main():
    st.write(
        f"""
        This tool is utilising PyLinac version `{_pylinac_installed.__version__}`
        for it's field and ball bearing position determination.
        """
    )

    st.sidebar.write("# Display options")
    bb_diameter = st.sidebar.number_input(
        "Ball bearing diameter (mm): ", min_value=0.0, max_value=None, value=8.0
    )
    penumbra = st.sidebar.number_input(
        "Field penumbra size (mm): ", min_value=0.0, max_value=None, value=2.0
    )
    expander = st.sidebar.beta_expander("Details")
    with expander:
        st.write(
            """
            Ball bearing diameter is utilised to draw a circle on the
            plot and to bound the x-axis on the flipped BB plots.

            The penumbra here is defined as the approximate distance
            between field's 50% line and the field's shoulder. It is
            utilised to shrink pylinac's radiation bounding box to
            display the a rectangle on the plot, and also to centre and
            scale the x-axis on the field edge flip displays.
            """
        )

    dicom_datasets = _loader.dicom_file_loader(
        accept_multiple_files=True, stop_before_pixels=False
    )

    if not st.button("Run Calculations"):
        st.stop()

    st.sidebar.write("# Progress")
    progress_bar = st.sidebar.progress(0)

    # TODO: Add in an updating Altair plot at the top...

    wl_images = []
    for i, dataset in enumerate(dicom_datasets):
        st.write(
            f"## Gantry: {dataset.GantryAngle:0.1f} | "
            f"Collimator: {dataset.BeamLimitingDeviceAngle:0.1f} | "
            f"Turn Table: {dataset.PatientSupportAngle:0.1f}"
        )
        wl_image = _nasty_wrapper_around_pylinac(dataset)
        wl_images.append(wl_image)

        progress_bar.progress((i + 1) / len(dicom_datasets))
        _display_wl_image(wl_image, bb_diameter, penumbra)


def _display_wl_image(wl_image, bb_diameter, penumbra):
    left, right = st.beta_columns(2)

    (
        x,
        y,
        image,
        bb_centre,
        field_centre,
        edge_lengths,
    ) = _display_parameters_from_wl_image(wl_image, penumbra)

    field_centre = np.array(field_centre)
    bb_centre = np.array(bb_centre)

    with left:
        st.write(
            f"""
            ### Details

            * Field centre: `{np.round(field_centre, 2)}`
            * BB centre: `{np.round(bb_centre, 2)}`
            * Field - BB: `{np.round(field_centre - bb_centre, 2)}`
            """
        )

    field_rotation = 0

    fig, _ = _reporting.image_analysis_figure(
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

    with right:
        st.pyplot(fig)


def _display_parameters_from_wl_image(wl_image, penumbra):
    centre = wl_image.center
    dpmm = wl_image.dpmm
    bb = wl_image.bb
    field = wl_image.field_cax

    image = wl_image.array
    x = (np.arange(image.shape[1]) - centre.x) / dpmm
    y = (np.arange(image.shape[0]) - centre.y) / dpmm

    bb_centre = _diff_to_centre(bb, centre, dpmm)
    field_centre = _diff_to_centre(field, centre, dpmm)

    y_length = (
        wl_image.rad_field_bounding_box[1] - wl_image.rad_field_bounding_box[0]
    ) / dpmm - 2 * penumbra
    x_length = (
        wl_image.rad_field_bounding_box[3] - wl_image.rad_field_bounding_box[2]
    ) / dpmm - 2 * penumbra

    edge_lengths = (x_length, y_length)

    return x, y, image, bb_centre, field_centre, edge_lengths


def _diff_to_centre(item, centre, dpmm):
    point = (item - centre) / dpmm
    if point.z != 0:
        raise ValueError("Only 2D points supported")

    return (point.x, point.y)


@st.cache(allow_output_mutation=True, show_spinner=True)
def _nasty_wrapper_around_pylinac(dataset):
    with tempfile.TemporaryDirectory() as temp_dir:
        dicom_file = pathlib.Path(temp_dir, "dicom_file.dcm")
        pydicom.dcmwrite(dicom_file, dataset)
        wl_image = _pylinac_installed.winston_lutz.WLImage(
            dicom_file, use_filenames=False
        )

    return wl_image
