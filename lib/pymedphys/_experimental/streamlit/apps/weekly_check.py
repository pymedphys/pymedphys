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

# from datetime import date, timedelta

from pymedphys._imports import pandas as pd
from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as st_config
from pymedphys._streamlit.utilities import mosaiq as _mosaiq

from pymedphys._experimental.chartchecks.compare import (
    specific_patient_weekly_check_colour_results,
    weekly_check_colour_results,
)
from pymedphys._experimental.chartchecks.weekly_check_helpers import (
    compare_all_incompletes,
    get_patient_image_info,
    plot_couch_deltas,
    plot_couch_positions,
    show_incomplete_weekly_checks,
)

CATEGORY = categories.PRE_ALPHA
TITLE = "Weekly Chart Review"


def select_patient(weekly_check_results):
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
    return patient_select


def main():
    config = st_config.get_config()
    connection = _mosaiq.get_single_mosaiq_connection_with_config(config)

    incomplete = show_incomplete_weekly_checks(connection)
    incomplete_qcls = incomplete.copy()
    incomplete_qcls = incomplete_qcls.drop_duplicates(subset=["patient_id"])
    # incomplete_qcls = incomplete_qcls.set_index("patient_id")

    all_delivered, weekly_check_results = compare_all_incompletes(
        connection, incomplete_qcls
    )[1:]
    all_delivered = all_delivered.astype({"pat_ID": "str"})
    weekly_check_results = weekly_check_results.sort_values(["first_name"])
    weekly_check_results = weekly_check_results.reset_index(drop=True)
    weekly_check_results_stylized = weekly_check_results.style.apply(
        weekly_check_colour_results, axis=1
    )
    st.table(weekly_check_results_stylized)

    patient_select = select_patient(weekly_check_results)

    if patient_select != "< Select a patient >":
        mrn = patient_select.split(",")[0]
        # planned, delivered, patient_results = compare_single_incomplete(mrn)
        todays_date = pd.Timestamp("today").floor("D")
        week_ago = todays_date + pd.offsets.Day(-7)
        delivered = all_delivered[all_delivered["mrn"] == mrn]
        # delivered_this_week = delivered
        delivered_this_week = delivered[delivered["date"] > week_ago]
        delivered_this_week = delivered_this_week.reset_index(drop=True)
        if delivered_this_week.empty:
            st.write("No recorded deliveries in the past week for this patient.")
            st.stop()
        # plot the couch coordinates for each delivered beam
        # st.write(planned)
        # st.write(delivered_this_week)
        st.header(
            delivered_this_week["first_name"].values[0]
            + " "
            + delivered_this_week["last_name"].values[0]
        )

        delivered_this_week["rx_change"] = 0
        for field in range(0, len(delivered_this_week)):
            if delivered_this_week.loc[field, "site_version"] != 0:
                delivered_this_week.loc[field, "rx_change"] = 1

        delivered_this_week["site_setup_change"] = 0
        for field in range(0, len(delivered_this_week)):
            if delivered_this_week.loc[field, "site_setup_version"] != 0:
                delivered_this_week.loc[field, "site_setup_change"] = 1

        fx_pattern = (
            delivered_this_week.groupby(["fx_pattern", "site"]).size().reset_index()
        )
        for i in range(0, len(fx_pattern)):
            st.write(
                "**",
                fx_pattern.iloc[i]["site"],
                "**",
                ": ",
                fx_pattern.iloc[i]["fx_pattern"],
            )

        st.table(
            delivered_this_week[
                [
                    "date",
                    "fx",
                    "total_dose_delivered",
                    "site",
                    "field_name",
                    "was_overridden",
                    "partial_tx",
                    "new_field",
                    "rx_change",
                    "site_setup_change",
                ]
            ].style.apply(specific_patient_weekly_check_colour_results, axis=1)
        )

        image_info_df = get_patient_image_info(connection, mrn)
        image_info_df = image_info_df[
            image_info_df["image_date"] > week_ago
        ].sort_values(["image_date"], ascending=False)
        st.write(image_info_df)

        # Create a checkbox to allow users to view treatment couch position history
        show_couch_positions = st.checkbox("Plot couch position history.")
        if show_couch_positions:
            plot_couch_positions(delivered)
            plot_couch_deltas(delivered)
