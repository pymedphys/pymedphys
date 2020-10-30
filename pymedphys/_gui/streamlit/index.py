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

import pathlib
from typing import Callable, cast

import streamlit as st

from pymedphys._gui.streamlit import mudensity

HERE = pathlib.Path(__file__).parent.resolve()
FAVICON = str(HERE.joinpath("pymedphys.png"))

st.set_page_config(
    page_title="PyMedPhys", page_icon=FAVICON, initial_sidebar_state="expanded"
)

parameters = st.experimental_get_query_params()

try:
    current_application = parameters["app"][0]
except KeyError:
    current_application = "index"


def index_main():
    """
    Please select an application above.
    """


application_options = {
    "index": {"label": "Index", "callable": index_main},
    "mudensity": {"label": "MU Density Comparison", "callable": mudensity.main},
}

app_keys = list(application_options.keys())
option_app_key_map = {
    application_options[app_key]["label"]: app_key for app_key in app_keys
}
options = list(option_app_key_map.keys())
default = options.index(application_options[current_application]["label"])

st.sidebar.write("# Application Selection")

selected_application_label = st.sidebar.selectbox(
    "Select application", options=options, index=default, key="application_index"
)
selected_application = option_app_key_map[selected_application_label]

st.experimental_set_query_params(app=selected_application)

app_main = cast(Callable, application_options[selected_application]["callable"])

app_main()
