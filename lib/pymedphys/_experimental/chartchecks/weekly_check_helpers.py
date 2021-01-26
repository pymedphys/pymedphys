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
from pymedphys._imports import plotly
from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_incomplete_qcls

from pymedphys._experimental.chartchecks.helpers import (
    get_all_treatment_data,
    get_all_treatment_history_data,
)


def show_incomplete_weekly_checks():
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        incomplete = get_incomplete_qcls(cursor, "Physics Resident")
        todays_date = date.today() + timedelta(days=3)
        todays_date = todays_date.strftime("%b %d, %Y")
        # todays_date = "Dec 4, 2020"
        incomplete = incomplete[
            (incomplete["task"] == "Weekly Chart Check")
            & (incomplete["due"] == todays_date)
        ]
        incomplete = incomplete.drop(columns=["instructions", "task", "due", "comment"])
        incomplete = incomplete.reset_index(drop=True)

    return incomplete


def compare_delivered_to_planned(patient):
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        delivered = get_all_treatment_history_data(cursor, patient)
        planned = get_all_treatment_data(cursor, patient)
        patient_results = pd.DataFrame()
        try:
            # current_fx = max(delivered_values["fx"])
            todays_date = pd.Timestamp("today").floor("D")
            week_ago = todays_date + pd.offsets.Day(-7)
            delivered_this_week = delivered.copy()
            delivered_this_week = delivered_this_week[delivered["date"] > week_ago]
        except (TypeError, ValueError, AttributeError):
            print("fraction field empty")
        primary_checks = {
            "patient_id": patient,
            "first_name": delivered_this_week.iloc[0]["first_name"],
            "last_name": delivered_this_week.iloc[0]["last_name"],
            "was_overridden": "",
            "new_field": "",
            "rx_change": "",
            "site_setup_change": "",
            "partial_tx": "",
        }

        if True in delivered_this_week["was_overridden"].values:
            primary_checks["was_overridden"] = "Treatment Overridden"

        if True in delivered_this_week["new_field"].values:
            primary_checks["new_field"] = "New Field Delivered"

        if not all(delivered_this_week["site_version"]) == 0:
            primary_checks["rx_change"] = "Prescription Altered"

        if not all(delivered_this_week["site_setup_version"]) == 0:
            primary_checks["site_setup_change"] = "Site Setup Altered"

        if True in delivered_this_week["partial_tx"].values:
            primary_checks["partial_tx"] = "Partial Treatment"

        for key, item in primary_checks.items():
            patient_results[key] = [item]

    return planned, delivered, patient_results


@st.cache(ttl=86400)
def compare_all_incompletes(incomplete_qcls):
    all_planned = pd.DataFrame()
    all_delivered = pd.DataFrame()
    overall_results = pd.DataFrame()
    if not incomplete_qcls.empty:
        for patient in incomplete_qcls["patient_id"]:
            (
                planned_values,
                delivered_values,
                patient_results,
            ) = compare_delivered_to_planned(patient)

            all_planned = all_planned.append(planned_values)
            all_delivered = all_delivered.append(delivered_values)
            overall_results = overall_results.append(patient_results)

        return all_planned, all_delivered, overall_results

    else:
        return None, None, "No weeklys due today, but thanks for trying."


def plot_couch_positions(delivered):
    delivered = delivered.drop_duplicates(subset=["fx"])
    delivered = delivered.reset_index(drop=True)
    couches = pd.DataFrame()
    couches_df = pd.DataFrame()
    for direction in ["couch_vrt", "couch_lat", "couch_lng"]:
        couches["fx"] = delivered.index
        couches["direction"] = direction
        couches["position"] = delivered[direction]
        couches_df = couches_df.append(couches)
        couches = pd.DataFrame()

    fig = plotly.express.scatter(couches_df, x="fx", y="position", color="direction")
    fig.update_layout(
        title="Couch Positions",
        yaxis_title="Difference from First Tx [cm]",
        xaxis_title="Fx",
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_couch_deltas(delivered):
    delivered = delivered.drop_duplicates(subset=["fx"])
    delivered = delivered.reset_index(drop=True)
    couches = pd.DataFrame()
    couches_df = pd.DataFrame()
    for direction in ["couch_vrt", "couch_lat", "couch_lng"]:
        couches["fx"] = delivered.index
        couches["direction"] = direction
        couches["position"] = delivered[direction]
        couches["diff"] = couches["position"] - couches.iloc[0]["position"]
        couches_df = couches_df.append(couches)
        couches = pd.DataFrame()

    fig = plotly.express.scatter(couches_df, x="fx", y="diff", color="direction")
    fig.update_layout(
        title="Couch Deltas for Each Beam On",
        yaxis_title="Difference from First Tx [cm]",
        xaxis_title="Fx",
    )
    st.plotly_chart(fig, use_container_width=True)
