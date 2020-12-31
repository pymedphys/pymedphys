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

OPPOSING_COLLIMATOR_TOLERANCE = 5  # degrees
AGREEING_GANTRY_TOLERANCE = 10  # degrees


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

    coll_combined = np.concatenate([coll_mod, coll_mod.T, coll_mod, coll_mod.T], axis=1)

    gantry_combined = np.concatenate(
        [gantry_mod, gantry_mod, gantry_mod.T, gantry_mod.T], axis=1
    )
    combined = coll_combined + gantry_combined

    index_of_min = np.argmin(combined, axis=1)
    min_coll_values = np.take_along_axis(coll_combined, index_of_min[:, None], axis=1)
    min_gantry_values = np.take_along_axis(
        gantry_combined, index_of_min[:, None], axis=1
    )

    out_of_tolerance = np.logical_or(
        min_coll_values > OPPOSING_COLLIMATOR_TOLERANCE,
        min_gantry_values > AGREEING_GANTRY_TOLERANCE,
    )

    st.write(min_coll_values)
    st.write(min_gantry_values)

    min_location_by_dataframe_row = np.mod(index_of_min, len(dataframe_by_treatment))

    st.write(min_location_by_dataframe_row)


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
