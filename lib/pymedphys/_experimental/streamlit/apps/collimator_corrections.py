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

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._experimental.streamlit.apps.wlutz import _utilities

CATEGORY = "experimental"
TITLE = "WLutz Collimator Processing"

ANGLE_AGREEMENT_TOLERANCE = 10  # degrees


def main():
    (
        _,
        _,
        wlutz_directory_by_date,
        _,
        _,
        _,
    ) = _utilities.get_directories_and_initial_database(refresh_cache=False)

    raw_results_csv_path = wlutz_directory_by_date.joinpath("raw_results.csv")

    st.write(f"`{raw_results_csv_path}`")

    try:
        dataframe = _get_results(raw_results_csv_path)
    except FileNotFoundError:
        st.error("Winston Lutz results not yet calculated/saved for this date.")
        st.stop()

    algorithm = "PyMedPhys"
    dataframe_by_algorithm = _filter_by(dataframe, "algorithm", algorithm)

    # st.write(dataframe)

    treatments = dataframe_by_algorithm["treatment"].unique()
    # st.write(treatments)

    treatment = treatments[0]
    # st.write(treatment)

    dataframe_by_treatment = _filter_by(dataframe_by_algorithm, "treatment", treatment)
    st.write(dataframe_by_treatment)

    collimator = dataframe_by_treatment["collimator"]
    st.write(collimator)

    gantry = dataframe_by_treatment["gantry"]

    gantry_mod = np.mod(gantry[:, None] - gantry[None, :], 360)
    coll_mod = np.mod(collimator[:, None] - collimator[None, :] + 180, 360)

    assert gantry_mod.shape == (
        len(dataframe_by_treatment),
        len(dataframe_by_treatment),
    )

    st.write(gantry_mod)
    st.write(coll_mod)

    combined = np.concatenate(
        [
            gantry_mod + coll_mod,
            gantry_mod + coll_mod.T,
            gantry_mod.T + coll_mod,
            gantry_mod.T + coll_mod.T,
        ],
        axis=1,
    )
    min_location = np.mod(np.argmin(combined, axis=1), len(dataframe_by_treatment))
    # min_location_coords = np.unravel_index(min_location, combined.shape)

    st.write(combined.shape)

    st.write(min_location)


@st.cache()
def _get_results(filepath) -> "pd.DataFrame":
    raw_results_dataframe = pd.read_csv(filepath)

    return raw_results_dataframe


# def _filter_by_column(dataframe, column):
#     options = list(dataframe[column].unique())
#     selected = st.radio(column, options)
#     filtered = dataframe.loc[dataframe[column] == selected]

#     return filtered


def _filter_by(dataframe, column, value):
    filtered = dataframe.loc[dataframe[column] == value]

    return filtered
