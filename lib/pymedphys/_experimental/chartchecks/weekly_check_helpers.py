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

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt
from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_incomplete_qcls

from pymedphys._experimental.chartchecks.helpers import (
    get_all_treatment_data,
    get_all_treatment_history_data,
)


def get_delivered_fields(patient):
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        delivered_values = get_all_treatment_history_data(cursor, patient)
    return delivered_values


def show_incomplete_weekly_checks():
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        incomplete_qcls = get_incomplete_qcls(cursor, "Physics Resident")
        todays_date = date.today() + timedelta(days=1)
        todays_date = todays_date.strftime("%b %d, %Y")
        # todays_date = "Dec 4, 2020"
        incomplete_qcls = incomplete_qcls[
            (incomplete_qcls["task"] == "Weekly Chart Check")
            & (incomplete_qcls["due"] == todays_date)
        ]
        incomplete_qcls = incomplete_qcls.drop(
            columns=["instructions", "task", "due", "comment"]
        )
        incomplete_qcls = incomplete_qcls.reset_index(drop=True)

    return incomplete_qcls


def compare_delivered_to_planned(patient):
    with connect.connect("PRDMOSAIQIWVV01.utmsa.local") as cursor:
        delivered_values = get_all_treatment_history_data(cursor, patient)
        planned_values = get_all_treatment_data(cursor, patient)
        patient_results = pd.DataFrame()
        try:
            # current_fx = max(delivered_values["fraction"])
            todays_date = pd.Timestamp("today").floor("D")
            week_ago = todays_date + pd.offsets.Day(-7)
            delivered_values = delivered_values[delivered_values["date"] > week_ago]
        except (TypeError, ValueError, AttributeError):
            print("fraction field empty")
        primary_checks = {
            "patient_id": patient,
            "was_overridden": "",
            "new_field": "",
            "rx_change": "",
            "site_setup_change": "",
            "partial_treatment": "",
        }

        if True in delivered_values["was_overridden"].values:
            primary_checks["was_overridden"] = "Treatment Overridden"

        if True in delivered_values["new_field"].values:
            primary_checks["new_field"] = "New Field Delivered"

        if not all(delivered_values["site_version"]) == 0:
            primary_checks["rx_change"] = "Prescription Altered"

        if not all(delivered_values["site_setup_version"]) == 0:
            primary_checks["site_setup_change"] = "Site Setup Altered"

        if True in delivered_values["partial_treatment"].values:
            primary_checks["partial_treatment"] = "Partial Treatment"

        for key, item in primary_checks.items():
            patient_results[key] = [item]

    # delivered_parameters = delivered_values.columns
    # planned_parameters = planned_values.columns
    # for field in range(0, len(delivered_values)):
    #     for parameter in delivered_parameters:
    #         if parameter in planned_parameters:
    #             field[parameter] ==

    return planned_values, delivered_values, patient_results


def compare_single_incomplete(patient):
    planned_values, delivered_values, patient_results = compare_delivered_to_planned(
        patient
    )
    return planned_values, delivered_values, patient_results


@st.cache(ttl=86400)
def compare_all_incompletes(incomplete_qcls):
    overall_results = pd.DataFrame()
    breakpoint()
    if not incomplete_qcls.empty:
        for patient in incomplete_qcls.index:
            patient_results = pd.DataFrame()
            (
                planned_values,
                delivered_values,
                patient_results,
            ) = compare_delivered_to_planned(patient)
            overall_results = overall_results.append(patient_results)

        return planned_values, delivered_values, overall_results

    else:
        return None, None, "No weeklys due today, but thanks for trying."


def plot_couch_positions(delivered):
    delivered = delivered.drop_duplicates(subset=["fraction"])
    delivered = delivered.reset_index(drop=True)

    fig, ax = plt.subplots()
    ax.scatter(
        delivered["couch_vrt"].index,
        delivered["couch_vrt"].values,
        label="couch_vrt",
        marker=".",
    )
    ax.axhline(
        np.mean(delivered["couch_vrt"].values) + np.std(delivered["couch_vrt"].values),
        color="blue",
        linestyle=":",
    )
    ax.axhline(
        np.mean(delivered["couch_vrt"].values) - np.std(delivered["couch_vrt"].values),
        color="blue",
        linestyle=":",
    )

    ax.scatter(
        delivered["couch_lat"].index,
        delivered["couch_lat"].values,
        label="couch_lat",
        marker=".",
    )
    ax.axhline(
        np.mean(delivered["couch_lat"].values) + np.std(delivered["couch_lat"].values),
        color="orange",
        linestyle=":",
    )
    ax.axhline(
        np.mean(delivered["couch_lat"].values) - np.std(delivered["couch_lat"].values),
        color="orange",
        linestyle=":",
    )

    ax.scatter(
        delivered["couch_lng"].index,
        delivered["couch_lng"].values,
        label="couch_lng",
        marker=".",
    )
    ax.axhline(
        np.mean(delivered["couch_lng"].values) + np.std(delivered["couch_lng"].values),
        color="green",
        linestyle=":",
    )
    ax.axhline(
        np.mean(delivered["couch_lng"].values) - np.std(delivered["couch_lng"].values),
        color="green",
        linestyle=":",
    )

    ax.set_title("Couch Positions for Each Beam On")
    ax.legend()
    st.pyplot(fig)
