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


from pymedphys._imports import numpy as np
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

from pymedphys._experimental.streamlit.utilities.iview import ui as iview_ui

from .wlutz import _calculation, _config, _corrections, _excel

CATEGORY = categories.ALPHA
TITLE = "Daily WLutz"


PROJECTION_TOLERANCE = 2.0  # mm
MEAN_TOLERANCE = 1.0  # mm


def main():
    bb_diameter = 12
    penumbra = 2
    advanced_mode = False
    loosen_internal_tolerances = True

    config = _config.get_config(False)

    (
        database_table,
        database_directory,
        qa_directory,
        selected_date,
    ) = iview_ui.iview_and_icom_filter_and_align(config, advanced_mode, quiet=True)

    wlutz_directory = qa_directory.joinpath("Winston-Lutz Results")
    wlutz_directory_by_date = wlutz_directory.joinpath(
        selected_date.strftime("%Y-%m-%d")
    )

    statistics_collection = _calculation.calculations_ui(
        database_table,
        database_directory,
        wlutz_directory_by_date,
        bb_diameter,
        penumbra,
        advanced_mode,
        loosen_internal_tolerances,
        quiet=True,
    )

    if statistics_collection is None:
        st.stop()

    passing_thus_far = True

    negative_projection_distance = np.max(np.abs(statistics_collection["min"]))
    positive_projection_distance = np.max(np.abs(statistics_collection["max"]))

    if (
        negative_projection_distance > PROJECTION_TOLERANCE
        or positive_projection_distance > PROJECTION_TOLERANCE
    ):
        passing_thus_far = False

    mean_distance = np.max(np.abs(statistics_collection["mean"]))

    if mean_distance > MEAN_TOLERANCE:
        passing_thus_far = False

    if passing_thus_far:
        st.sidebar.success("Daily WLutz QA was a success! 🥳🎉")
    else:
        st.sidebar.error("Daily WLutz QA was out of tolerance. 😞")

    st.write(statistics_collection)
