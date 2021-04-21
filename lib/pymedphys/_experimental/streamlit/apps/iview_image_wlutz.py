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
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.wlutz import iview as _iview
from pymedphys._experimental.wlutz import main as _main
from pymedphys._experimental.wlutz import reporting as _reporting

CATEGORY = categories.PLANNING
TITLE = "iView Image WLutz"


def main():
    a_file = st.file_uploader("iView images 'jpg' file")

    zoom_factor = st.slider("Zoom factor", 1, 32, value=4)
    ignore_errors = st.checkbox("Ignore errors", False)

    if a_file is None:
        st.stop()

    a_file.seek(0)
    img_raw = libjpeg.decode(a_file.read())
    x, y, image = _iview.iview_image_transform(img_raw)
    image = 1 - image

    options = {
        "bb_diameter": 12,
        "edge_lengths": (100, 100),
        "penumbra": 2,
    }

    field_centre, bb_centre = _main._pymedphys_wlutz_calculate(
        x,
        y,
        image,
        fill_errors_with_nan=ignore_errors,
        icom_field_rotation=0,
        **options,
    )

    fig, axs = _reporting.image_analysis_figure(
        x,
        y,
        image,
        bb_centre,
        field_centre,
        field_rotation=0,
        **options,
    )

    ylim = np.array(axs[0, 0].get_ylim())
    xlim = np.array(axs[0, 0].get_xlim())

    axs[0, 0].set_ylim(ylim / zoom_factor)
    axs[0, 0].set_xlim(xlim / zoom_factor)

    st.pyplot(fig)
