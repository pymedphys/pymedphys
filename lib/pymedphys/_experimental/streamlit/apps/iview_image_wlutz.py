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


from pymedphys._imports import libjpeg
from pymedphys._imports import numpy as np
from pymedphys._imports import scipy
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.wlutz import iview as _iview
from pymedphys._experimental.wlutz import main as _main
from pymedphys._experimental.wlutz import reporting as _reporting

CATEGORY = categories.ALPHA
TITLE = "iView Image WLutz"


def main():
    """A tool for uploading individual iView backend image files and
    undergoing ball-bearing and field edge detection.

    Provides a facilities to tweak the back-end WLutz algorithm
    to investigate the impact of these adjustments. This application
    was originally written for the purpose of investigating the
    plausibility of detecting an air-cavity instead of a ball-bearing
    for utilising the WLutz algorithm for daily QA with the already
    utilised during the morning kV image and couch movement tests.
    """
    a_file = st.file_uploader("iView images 'jpg' file")

    ignore_errors = st.checkbox("Ignore errors", False)
    apply_median_filter = st.checkbox("Apply 3x3 median filter", False)
    apply_gaussian_filter = st.checkbox(
        "Apply 1 pixel width sigma gaussian filter", False
    )
    zoom_factor = st.slider("Zoom factor", 1.0, 16.0, value=1.0)
    bb_repeats = st.number_input(
        "Number of repeat BB finding attempts", min_value=0, max_value=20, value=6
    )
    bb_consistency_tolerance = st.number_input(
        "BB consistency tolerance (mm)", min_value=0.0, max_value=1000.0, value=1.0
    )

    field_edge_x = st.number_input(
        "Field edge x size (mm)", min_value=5.0, max_value=400.0, value=30.0
    )
    field_edge_y = st.number_input(
        "Field edge y size (mm)", min_value=5.0, max_value=400.0, value=30.0
    )

    if a_file is None:
        st.stop()

    a_file.seek(0)
    img_raw = libjpeg.decode(a_file.read())
    x, y, image = _iview.iview_image_transform(img_raw)

    if apply_median_filter:
        image = scipy.ndimage.median_filter(image, size=3)

    if apply_gaussian_filter:
        image = scipy.ndimage.gaussian_filter(image, sigma=1)

    vmin_default = float(np.min(image))
    vmax_default = float(np.max(image))

    vmin, vmax = st.slider(
        "Colour range",
        min_value=vmin_default,
        max_value=vmax_default,
        value=(vmin_default, vmax_default),
    )

    options = {
        "bb_diameter": 12,
        "edge_lengths": (field_edge_x, field_edge_y),
        "penumbra": 2,
    }

    field_centre, bb_centre = _main.pymedphys_wlutz_calculate(
        x,
        y,
        image,
        fill_errors_with_nan=ignore_errors,
        icom_field_rotation=0,
        bb_repeats=bb_repeats,
        bb_consistency_tol=bb_consistency_tolerance,
        **options,
    )

    diff = field_centre - bb_centre
    st.write(
        f"""
        ## Results

        Field - BB (or air-gap) centre

        * x deviation: `{diff[0]:.2f} mm`
        * y deviation: `{diff[1]:.2f} mm`
        """
    )

    fig, axs = _reporting.image_analysis_figure(
        x,
        y,
        image,
        bb_centre,
        field_centre,
        field_rotation=0,
        vmin=vmin,
        vmax=vmax,
        **options,
    )

    ylim = np.array(axs[0, 0].get_ylim())
    xlim = np.array(axs[0, 0].get_xlim())

    axs[0, 0].set_ylim(ylim / zoom_factor)
    axs[0, 0].set_xlim(xlim / zoom_factor)

    st.pyplot(fig)
