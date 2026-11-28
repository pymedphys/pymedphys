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


import pymedphys


# Treatment deliveries may contain patient-specific data and can change when
# their source files or database records are updated. Do not share the parsed
# results between independent Streamlit sessions.
def delivery_from_trf(pandas_table):
    return pymedphys.Delivery._from_pandas(  # pylint: disable = protected-access
        pandas_table
    )


def delivery_from_icom(icom_stream):
    return pymedphys.Delivery.from_icom(icom_stream)


def delivery_from_tel(tel_path):
    return pymedphys.Delivery.from_monaco(tel_path)


def delivery_from_mosaiq(connection_and_field_id):
    connection, field_id = connection_and_field_id
    return pymedphys.Delivery.from_mosaiq(connection, field_id)


def cached_deliveries_loading(inputs, method_function):
    deliveries = []

    for an_input in inputs:
        deliveries += [method_function(an_input)]

    return deliveries
