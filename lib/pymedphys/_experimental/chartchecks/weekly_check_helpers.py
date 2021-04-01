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

import collections

from pymedphys._imports import pandas as pd
from pymedphys._imports import plotly
from pymedphys._imports import streamlit as st

import pymedphys
import pymedphys._mosaiq.api as _pp_mosaiq
from pymedphys._mosaiq.helpers import get_incomplete_qcls

from pymedphys._experimental.chartchecks.helpers import (
    get_all_mosaiq_treatment_data,
    get_all_treatment_history_data,
)

from .tolerance_constants import IMAGE_APPROVAL


def show_incomplete_weekly_checks(connection):

    all_incomplete = get_incomplete_qcls(connection, "Physics Resident")
    todays_date = pd.Timestamp("today").floor("D") + pd.Timedelta(value=3, unit="D")

    incomplete_weekly = all_incomplete.copy()
    incomplete_weekly = incomplete_weekly[
        (incomplete_weekly["task"] == "Weekly Chart Check")
        & (incomplete_weekly["due"] == todays_date)
    ]
    incomplete_weekly = incomplete_weekly.drop(
        columns=["instructions", "task", "due", "comment"]
    )
    incomplete_weekly = incomplete_weekly.reset_index(drop=True)
    if incomplete_weekly.empty:
        st.write("No weekly chart checks due today.")
        st.stop()
    return incomplete_weekly


def compare_delivered_to_planned(connection, patient):
    delivered = get_all_treatment_history_data(connection, patient)
    planned = get_all_mosaiq_treatment_data(connection, patient)
    patient_results = pd.DataFrame()
    try:
        # current_fx = max(delivered_values["fx"])
        todays_date = pd.Timestamp("today").floor("D") + pd.Timedelta(value=0, unit="D")
        week_ago = todays_date - pd.Timedelta(value=7, unit="D")
        delivered_this_week = delivered.copy()
        delivered_this_week = delivered_this_week[
            delivered_this_week["date"] > week_ago
        ]
    except (TypeError, ValueError, AttributeError):
        print("fraction field empty")
    primary_checks = {
        "patient_id": patient,
        "first_name": planned["first_name"].values[0],
        "last_name": planned["last_name"].values[0],
        "was_overridden": "",
        "new_field": "",
        "rx_change": "",
        "site_setup_change": "",
        "partial_tx": "",
        "notes": "",
    }

    if delivered_this_week.empty:
        primary_checks["notes"] = "No recorded treatments within last week."
        for key, item in primary_checks.items():
            patient_results[key] = [item]
        return planned, delivered, patient_results

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


@st.cache(ttl=86400, hash_funcs={pymedphys.mosaiq.Connection: id})
def compare_all_incompletes(connection, incomplete_qcls):
    all_planned = pd.DataFrame()
    all_delivered = pd.DataFrame()
    overall_results = pd.DataFrame()
    if not incomplete_qcls.empty:
        for patient in incomplete_qcls["patient_id"]:
            (
                planned_values,
                delivered_values,
                patient_results,
            ) = compare_delivered_to_planned(connection, patient)

            all_planned = all_planned.append(planned_values)
            all_delivered = all_delivered.append(delivered_values)
            overall_results = overall_results.append(patient_results)

        return all_planned, all_delivered, overall_results

    else:
        st.write("There are no incomplete QCLs.")
        return st.stop()


def plot_couch_positions(delivered):
    delivered = delivered.drop_duplicates(subset=["fx"])
    delivered = delivered.reset_index(drop=True)
    couches = pd.DataFrame()
    couches_df = pd.DataFrame()
    for direction in ["couch_vrt", "couch_lat", "couch_lng"]:
        couches["fx"] = delivered["fx"]
        couches["direction"] = direction
        couches["position"] = delivered[direction]
        couches_df = couches_df.append(couches)
        couches = pd.DataFrame()

    couch_fig = plotly.express.scatter(
        couches_df, x="fx", y="position", color="direction"
    )
    couch_fig.update_layout(
        title="<b>Couch Positions<b>",
        yaxis_title="Couch Position [cm]",
        xaxis_title="Fx",
        xaxis=dict(tickmode="linear", tick0=0, dtick=1),
    )
    st.plotly_chart(couch_fig, use_container_width=True)


def plot_couch_deltas(delivered):
    delivered = delivered.drop_duplicates(subset=["fx"])
    delivered = delivered.reset_index(drop=True)
    couches = pd.DataFrame()
    couches_df = pd.DataFrame()
    for direction in ["couch_vrt", "couch_lat", "couch_lng"]:
        couches["fx"] = delivered["fx"]
        couches["direction"] = direction
        couches["position"] = delivered[direction]
        couches["diff"] = couches["position"] - couches.iloc[0]["position"]
        couches_df = couches_df.append(couches)
        couches = pd.DataFrame()

    deltas_fig = plotly.express.scatter(couches_df, x="fx", y="diff", color="direction")
    deltas_fig.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="LightPink")
    deltas_fig.update_layout(
        title="<b>Couch Deltas for Each Beam On<b>",
        yaxis_title="Difference from First Tx [cm]",
        xaxis_title="Fx",
        xaxis=dict(tickmode="linear", tick0=0, dtick=1),
    )
    st.plotly_chart(deltas_fig, use_container_width=True)


def get_patient_image_info(connection, patient):
    dataframe_column_to_sql_reference = collections.OrderedDict(
        [
            ("image_date", "Image.Study_DtTm"),
            ("type", "Image.Short_Name"),
            ("name", "Image.Image_Name"),
            ("label", "Image.Field_Label"),
            ("num_images", "Image.Num_Images"),
            ("comments", "Image.Comments"),
            ("review_status", "Image.Att_App"),
            ("review_id", "Image.Att_Apper_ID"),
            ("device", "Image.Imager_Name"),
            ("machine", "Image.Machine_Name"),
        ]
    )

    columns = list(dataframe_column_to_sql_reference.keys())
    select_string = "SELECT " + ",\n\t\t    ".join(
        dataframe_column_to_sql_reference.values()
    )

    sql_string = (
        select_string
        + """
        From Image, Ident
        WHERE
        Ident.IDA = %(mrn)s AND
        Ident.Pat_ID1 = Image.Pat_ID1
        """,
    )
    # select_string = "SELECT Image.* FROM Image, Ident WHERE Ident.IDA = %(patient)s AND Image.Pat_ID1 = Ident.Pat_ID1"
    image_info = _pp_mosaiq.execute(
        connection,
        sql_string[0],
        parameters={"mrn": patient},
    )

    image_info_df = pd.DataFrame(data=image_info, columns=columns)

    image_info_df["review_status"] = [
        IMAGE_APPROVAL[item] for item in image_info_df["review_status"]
    ]

    return image_info_df
