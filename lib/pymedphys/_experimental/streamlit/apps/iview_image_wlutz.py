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


from pymedphys._imports import libjpeg, plt
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.wlutz import iview as _iview
from pymedphys._experimental.wlutz import main as _main
from pymedphys._experimental.wlutz import reporting as _reporting

CATEGORY = categories.PLANNING
TITLE = "iView Image WLutz"


def main():
    a_file = st.file_uploader("iView images 'jpg' file")

    if a_file is None:
        st.stop()

    a_file.seek(0)
    img_raw = libjpeg.decode(a_file.read())
    x, y, image = _iview.iview_image_transform(img_raw)

    options = {
        "bb_diameter": 8,
        "edge_lengths": (100, 100),
        "penumbra": 2,
    }

    field_centre, bb_centre = _main._pymedphys_wlutz_calculate(
        x,
        y,
        image,
        fill_errors_with_nan=True,
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

    st.pyplot(fig)
