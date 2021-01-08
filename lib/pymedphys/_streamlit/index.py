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

import functools
import pathlib
import re
import time

from pymedphys._imports import PIL
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import apps as _stable_apps
from pymedphys._streamlit.apps import metersetmap, pseudonymise
from pymedphys._streamlit.utilities import session

from pymedphys._experimental.streamlit import apps as _experimental_apps
from pymedphys._experimental.streamlit.apps import (
    anonymise_monaco,
    collimator_corrections,
    dashboard,
    electrons,
    icom,
    iviewdb,
    transfer_check,
    weekly_check,
    wlutz,
    xlsxwriter,
)

HERE = pathlib.Path(__file__).parent.resolve()
FAVICON = str(HERE.joinpath("pymedphys-favicon.png"))
TITLE_LOGO = str(HERE.joinpath("pymedphys-title.png"))

# Utilise the PyPI development status classification scheme
APPLICATION_CATEGORIES = [
    "Mature",
    "Production/Stable",
    "Beta",
    "Alpha",
    "Pre-Alpha",
    "Planning",
]


def get_url_app():
    try:
        return st.experimental_get_query_params()["app"][0]
    except KeyError:
        return "index"


def swap_app(app):
    st.experimental_set_query_params(app=app)

    session_state = session.session_state()
    session_state.app = app

    # Not sure why this is needed. The `set_query_params` doesn't
    # appear to work if a rerun is undergone immediately afterwards.
    time.sleep(0.01)
    st.experimental_rerun()


def index(application_options):
    st.image(PIL.Image.open(TITLE_LOGO))

    title_filter = st.text_input("Filter")
    pattern = re.compile(f".*{title_filter}.*", re.IGNORECASE)

    for category in APPLICATION_CATEGORIES:
        applications_in_this_category = [
            item
            for item in application_options.items()
            if item[1].CATEGORY == category and pattern.match(item[1].TITLE)
        ]

        if not title_filter or applications_in_this_category:
            st.write(
                f"""
                    ## {category}
                """
            )

        if not applications_in_this_category and not title_filter:
            st.write("> *No applications are currently in this category.*")
            continue

        applications_in_this_category = sorted(
            applications_in_this_category, key=_application_sorting_key
        )

        for app_key, application in applications_in_this_category:
            if st.button(application.TITLE):
                swap_app(app_key)


def _application_sorting_key(application):
    return application[1].TITLE.lower()


def _get_apps_from_module(module):
    apps = {
        item.replace("_", "-"): getattr(module, item)
        for item in dir(module)
        if not item.startswith("_")
    }

    return apps


def main():
    st.set_page_config(page_title="PyMedPhys", page_icon=FAVICON)
    session_state = session.session_state(app=get_url_app())

    stable_apps = _get_apps_from_module(_stable_apps)
    experimental_apps = _get_apps_from_module(_experimental_apps)

    application_options = {**stable_apps, **experimental_apps}

    if (
        session_state.app != "index"
        and not session_state.app in application_options.keys()
    ):
        swap_app("index")

    if session_state.app != "index":
        st.title(application_options[session_state.app].TITLE)
        if st.sidebar.button("Return to Index"):
            swap_app("index")

        st.sidebar.write("---")

    if session_state.app == "index":
        application_function = functools.partial(
            index, application_options=application_options
        )
    else:
        application_function = application_options[session_state.app].main

    application_function()


if __name__ == "__main__":
    main()
