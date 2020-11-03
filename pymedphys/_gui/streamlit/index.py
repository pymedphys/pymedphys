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

import pathlib

import streamlit as st

from pymedphys._gui.streamlit.mudensity import main as _mudensity

HERE = pathlib.Path(__file__).parent.resolve()
FAVICON = str(HERE.joinpath("pymedphys.png"))

APPLICATION_CATEGORIES = {
    "mature": {
        "title": "Mature",
        "description": """
            These are mature applications. They are in wide use, and
            they have a high level of automated test coverage.
        """,
    },
    "maturing": {
        "title": "Maturing",
        "description": """
            These are relatively new applications. They potentially
            only have limited use within the community, but the still
            adhere to high quality standards with a level of automated
            test coverage that can be expected for a mature application.
        """,
    },
    "fresh": {
        "title": "Fresh",
        "description": """
            These are relatively new applications. They possibly only
            have minimal use, and they have at least some automated test
            coverage. It is likely that these applications and their
            respective configurations will still be changing as time
            goes on.
        """,
    },
    "beta": {
        "title": "Beta",
        "description": """
            These applications may not be in use at all within the
            community. They potentially may only have minimal automated
            test coverage.
        """,
    },
    "experimental": {
        "title": "Experimental",
        "description": """
            These applications may not be in use at all within the
            community and they may not have any automated test coverage.
        """,
    },
}


APPLICATION_OPTIONS = {
    "index": {
        "category": "experimental",
        "label": "Index",
        # A placeholder to be overridden by the index function below
        "callable": lambda: None,
    },
    "mudensity": {
        "category": "fresh",
        "label": "MU Density Comparison",
        "callable": _mudensity.main,
    },
}

st.set_page_config(
    page_title="PyMedPhys", page_icon=FAVICON, initial_sidebar_state="expanded"
)


def index():
    st.write(
        """
        # Index of applications available

        The following applications are organised by category where each
        category is representative of the maturity of the tool.
        """
    )

    for key, category in APPLICATION_CATEGORIES.items():
        st.write(
            f"""
                ## {category["title"]}
                {category["description"]}
            """
        )

        for application in APPLICATION_OPTIONS.values():
            if application["category"] == key:
                if st.button(application["label"]):
                    pass


APPLICATION_OPTIONS["index"]["callable"] = index


def selectbox_format(key):
    return APPLICATION_OPTIONS[key]["label"]


def main():
    st.sidebar.write("# GUI Select")

    selected_gui = st.sidebar.selectbox(
        "",
        list(APPLICATION_OPTIONS.keys()),
        format_func=selectbox_format,
        key="GUI_select_box",
    )

    st.sidebar.write("---")

    application_function = APPLICATION_OPTIONS[selected_gui]["callable"]
    application_function()


if __name__ == "__main__":
    main()
