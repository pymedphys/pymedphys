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


import datetime

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd  # pylint: disable = unused-import
from pymedphys._imports import streamlit as st


def filter_image_sets(
    to_be_filtered: "pd.DataFrame",
    advanced_mode: bool,
    quiet=False,
) -> "pd.DataFrame":
    """Filter an iView image set pandas DataFrame via streamlit user input.

    Filtering is undergone by machine_id, patient_id, datetime,
    treatment, and ports. This filtering is undergone via streamlit
    widgets.

    """
    filtered = to_be_filtered

    if not quiet:
        # Machine ID
        machine_id = st.radio("Machine", filtered["machine_id"].unique())
        filtered = filtered.loc[filtered["machine_id"] == machine_id]

    # Patient ID
    patient_ids = filtered["patient_id"].unique()
    if quiet and len(patient_ids) == 1:
        patient_id = patient_ids[0]
    else:
        patient_id = st.radio("Patient", filtered["patient_id"].unique())

    filtered = filtered.loc[filtered["patient_id"] == patient_id]

    if advanced_mode:
        # Time
        time = filtered["datetime"].dt.time

        time_step = datetime.timedelta(minutes=1)
        min_time = (np.min(filtered["datetime"])).floor("min").time()
        max_time = (np.max(filtered["datetime"])).ceil("min").time()

        time_range = st.slider(
            "Time",
            min_value=min_time,
            max_value=max_time,
            step=time_step,
            value=[min_time, max_time],
        )

        filtered = filtered.loc[(time >= time_range[0]) & (time <= time_range[1])]

        # Treatments
        unique_treatments = filtered["treatment"].unique().tolist()
        selected_treatments = st.multiselect(
            "Treatment", unique_treatments, default=sorted(unique_treatments)
        )
        filtered = filtered.loc[filtered["treatment"].isin(selected_treatments)]

        # Ports
        unique_ports = filtered["port"].unique().tolist()
        selected_ports = st.multiselect(
            "Ports", unique_ports, default=sorted(unique_ports)
        )
        filtered = filtered.loc[filtered["port"].isin(selected_ports)]

    return filtered
