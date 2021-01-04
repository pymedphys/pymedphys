# Copyright (C) 2020 Jacob Rembish

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import date, timedelta

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._experimental.chartchecks.compare import weekly_check_color_results
from pymedphys._experimental.chartchecks.weekly_check_helpers import (
    compare_all_incompletes,
    get_delivered_fields,
    plot_couch_positions,
    show_incomplete_weekly_checks,
)

CATEGORY = "experimental"
TITLE = "Weekly Chart Review"


def main():
    # currdir = os.getcwd()

    st.title("Weekly Check")

    incomplete_qcls = show_incomplete_weekly_checks()
    incomplete_qcls = incomplete_qcls.drop_duplicates(subset=["patient_id"])
    incomplete_qcls = incomplete_qcls.set_index("patient_id")

    delivered, overall_results = compare_all_incompletes(incomplete_qcls)[1:]
    overall_results = overall_results.set_index("patient_id")

    weekly_check_results = pd.concat(
        [incomplete_qcls, overall_results], axis=1, sort=True
    )
    weekly_check_results = weekly_check_results.sort_values(["first_name"])
    weekly_check_results = weekly_check_results.reset_index()
    weekly_check_results_stylized = weekly_check_results.style.apply(
        weekly_check_color_results, axis=1
    )
    st.write(weekly_check_results_stylized)

    default = pd.DataFrame(["< Select a patient >"])
    patient_list = (
        weekly_check_results["patient_id"]
        + ", "
        + weekly_check_results["first_name"]
        + " "
        + weekly_check_results["last_name"]
    )
    patient_list = pd.concat([default, patient_list]).reset_index(drop=True)
    patient_select = st.selectbox("Select a patient: ", patient_list[0])

    if patient_select != "< Select a patient >":
        mrn = patient_select.split(",")[0]
        # planned, delivered, patient_results = compare_single_incomplete(mrn)
        todays_date = date.today()
        week_ago = timedelta(days=7)
        delivered = get_delivered_fields(mrn)
        delivered_this_week = delivered[delivered["date"] > todays_date - week_ago]

        # plot the couch coordinates for each delivered beam
        # st.write(planned)
        # st.write(delivered_this_week)
        st.header(
            delivered_this_week.iloc[0]["first_name"]
            + " "
            + delivered_this_week.iloc[0]["last_name"]
        )
        st.write(
            delivered_this_week[
                [
                    "date",
                    "fraction",
                    "total_dose_delivered",
                    "site",
                    "field_name",
                    "was_overridden",
                    "partial_treatment",
                    "new_field",
                ]
            ].style.background_gradient(cmap="Greys")
        )
        # st.write(delivered)
        # st.write(patient_results)

        plot_couch_positions(delivered)
