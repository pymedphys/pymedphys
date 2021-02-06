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

import io
import pathlib

from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import download

CATEGORY = categories.PLANNING
TITLE = "Download Demo"

THIS = pathlib.Path(__file__).resolve()


def main():
    st.write(
        "This is a demo Streamlit app showing how to use the "
        "`download` function. The docstring for the "
        "`download` function is as follows:"
    )

    st.code(download.__doc__)

    st.write("## Example uses of `download`")

    st.write("### Download this very Python file")

    with open(THIS) as f:
        download(THIS.name, f.read())

    st.write("### Download a text file")
    download("a_text_file.txt", "Some beautiful text!")

    st.write("### Download a matplotlib figure")
    left, right = st.beta_columns(2)

    fig, ax = plt.subplots()
    ax.plot([-1, 0, 1], [1, -1, 1])

    with left:
        st.pyplot(fig)

    with right:
        _download_figure("plot.png", fig)


def _download_figure(name, fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format=name.split(".")[-1])
    buffer.seek(0)
    download(name, buffer.read())
