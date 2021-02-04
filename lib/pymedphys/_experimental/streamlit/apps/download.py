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

from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.server.downloads import download

CATEGORY = categories.PLANNING
TITLE = "DICOM Explorer"

THIS = pathlib.Path(__file__).resolve()


def main():
    st.write("Hello World!")

    download("download.py", THIS)
