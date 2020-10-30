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


# pylint: disable = no-member

import pathlib

import streamlit as st

from pymedphys._gui.streamlit import mudensity

HERE = pathlib.Path(__file__).parent.resolve()
FAVICON = str(HERE.joinpath("pymedphys.png"))


APPLICATION_OPTIONS = {
    "mudensity": {"label": "MU Density Comparison", "callable": mudensity.main}
}


def get_application():
    parameters = st.experimental_get_query_params()

    try:
        application = parameters["app"][0]
    except KeyError:
        application = "index"

    return application


def index_main():
    app_keys = list(APPLICATION_OPTIONS.keys())

    for app_key in app_keys:
        st.markdown(f"[{APPLICATION_OPTIONS[app_key]['label']}](?app={app_key})")


def run():
    st.set_page_config(page_title="PyMedPhys", page_icon=FAVICON)
    application = get_application()

    if application == "index":
        index_main()
    else:
        APPLICATION_OPTIONS[application]["callable"]()  # type: ignore


if __name__ == "__main__":
    run()
