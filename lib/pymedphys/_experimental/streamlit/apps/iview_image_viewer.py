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

CATEGORY = categories.ALPHA
TITLE = "iView Image Viewer"


def main():
    """A viewer for the back-end iView `.jpg` files.

    The backend iView `.jpg` files are encoded in a format that is
    rarely supported within modern software (1993 Lossless JPEG).
    As such, opening these
    files using standard image software can be troublesome. This tool
    was written to be able to readily view these files.
    """
    a_file = st.file_uploader("iView images 'jpg' file")

    if a_file is None:
        st.stop()

    a_file.seek(0)
    img_raw = libjpeg.decode(a_file.read())
    x, y, image = _iview.iview_image_transform(img_raw)

    fig, ax = plt.subplots()
    ax.pcolormesh(x, y, image)
    ax.axis("equal")
    st.pyplot(fig)

    half_dimension = image.shape[0] // 2

    zoom_selection = st.slider(
        "Zoom in on central region",
        min_value=1,
        max_value=half_dimension,
        value=half_dimension // 4,
    )
    zoom_slice = slice(half_dimension - zoom_selection, half_dimension + zoom_selection)

    fig, ax = plt.subplots()
    ax.pcolormesh(x[zoom_slice], y[zoom_slice], image[zoom_slice, zoom_slice])
    ax.axis("equal")
    st.pyplot(fig)
