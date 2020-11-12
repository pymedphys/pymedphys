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

from pymedphys._imports import keyring, pymssql
from pymedphys._imports import streamlit as st

from pymedphys._mosaiq import helpers as msq_helpers
from pymedphys._streamlit.apps.metersetmap import _config, _deliveries
from pymedphys._streamlit.utilities import misc as st_misc
from pymedphys._streamlit.utilities import mosaiq as st_mosaiq


@st.cache(hash_funcs={pymssql.Cursor: id})
def get_patient_fields(cursor, patient_id):
    return msq_helpers.get_patient_fields(cursor, patient_id)


@st.cache(hash_funcs={pymssql.Cursor: id})
def get_patient_name(cursor, patient_id):
    return msq_helpers.get_patient_name(cursor, patient_id)


def mosaiq_input_method(patient_id="", key_namespace="", site=None, **_):
    mosaiq_details = _config.get_mosaiq_details()

    mosaiq_site = st_misc.site_picker(
        "Mosaiq Site", default=site, key=f"{key_namespace}_mosaiq_site"
    )

    server = mosaiq_details[mosaiq_site]["server"]
    st.write(f"Mosaiq Hostname: `{server}`")

    sql_user = keyring.get_password("MosaiqSQL_username", server)
    st.write(f"Mosaiq SQL login being used: `{sql_user}`")

    patient_id = st.text_input(
        "Patient ID", patient_id, key=f"{key_namespace}_patient_id"
    )
    st.write(patient_id)

    cursor = st_mosaiq.get_mosaiq_cursor(server)

    if patient_id == "":
        return {}

    patient_name = get_patient_name(cursor, patient_id)

    st.write(f"Patient Name: `{patient_name}`")

    patient_fields = get_patient_fields(cursor, patient_id)

    st.write(
        """
        #### Mosaiq patient fields
        """
    )

    patient_fields = patient_fields[patient_fields["monitor_units"] != 0]
    st.write(patient_fields)

    field_ids = patient_fields["field_id"]
    field_ids = field_ids.values.tolist()

    selected_field_ids = st.multiselect(
        "Select Mosaiq field id(s)", field_ids, key=f"{key_namespace}_mosaiq_field_id"
    )

    cursor_and_field_ids = [(cursor, field_id) for field_id in selected_field_ids]
    deliveries = _deliveries.cached_deliveries_loading(
        cursor_and_field_ids, _deliveries.delivery_from_mosaiq
    )
    identifier = f"{mosaiq_site} Mosaiq ({', '.join([str(field_id) for field_id in selected_field_ids])})"

    return {
        "site": mosaiq_site,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "data_paths": [],
        "identifier": identifier,
        "deliveries": deliveries,
    }
