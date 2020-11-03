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
        "description": (
            "Mature application, in wide use, with high automated test coverage"
        ),
    },
    "maturing": {
        "title": "Maturing",
        "description": (
            "New application, potentially only limited use, with high "
            "automated test coverage"
        ),
    },
    "fresh": {
        "title": "Fresh",
        "description": (
            "New application, possibly only has minimal use, with some "
            "automated test coverage"
        ),
    },
    "beta": {
        "title": "Beta",
        "description": (
            "May not be in use at all, potentially only has minimal "
            "automated test coverage"
        ),
    },
    "experimental": {
        "title": "Experimental",
        "description": (
            "May not be in use at all, may not have any automated test coverage"
        ),
    },
}


APPLICATION_OPTIONS = {
    "mudensity": {
        "category": "fresh",
        "label": "MU Density Comparison",
        "callable": _mudensity.main,
    }
}


def main():
    st.set_page_config(page_title="PyMedPhys", page_icon=FAVICON)
    _mudensity.main()


if __name__ == "__main__":
    main()
