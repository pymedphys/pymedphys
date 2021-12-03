# Copyright (C) 2021 Derek Lane, Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pytest

import pymedphys
from pymedphys._mosaiq import delivery, helpers

from . import _connect
from .data import mocks


@pytest.fixture(name="connection")
def fixture_check_create_test_db() -> pymedphys.mosaiq.Connection:
    """ will create the test database, if it does not already exist on the instance """
    mocks.check_create_test_db()

    return _connect.connect()


@pytest.mark.mosaiqdb
def test_get_patient_name(connection: pymedphys.mosaiq.Connection):
    """ tests the get_patient_name helper function"""
    mocks.create_mock_patients()

    # test a generic query for patient info
    result_all = pymedphys.mosaiq.execute(
        connection,
        """
        SELECT
            Pat_Id1,
            First_Name,
            Last_Name
        FROM Patient
        """,
    )

    # show us the patients
    for patient in result_all:
        pat_id1, first_name, last_name = patient
        print(f"Pat_ID1:{pat_id1}  First Name:{first_name}  Last Name:{last_name}")

    # and check that the correct number were created
    assert len(result_all) == 3

    # test the get_patient_name helper function
    moe_patient_name = helpers.get_patient_name(connection, "MR8002")

    # finally spot check Moe
    assert moe_patient_name == "HOWARD, Moe"


@pytest.mark.mosaiqdb
def test_get_patient_fields(connection: pymedphys.mosaiq.Connection):
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    mock_patient_ident_df = mocks.create_mock_patients()
    mock_site_df = mocks.create_mock_treatment_sites(mock_patient_ident_df)
    mocks.create_mock_treatment_fields(mock_site_df)

    # test the get_patient_fields helper function
    fields_for_moe_df = helpers.get_patient_fields(connection, "MR8002")
    print(fields_for_moe_df)

    # make sure the correct number of rows were returned
    # with the rng seed, there are 4 fields created for moe
    field_count = 3
    assert len(fields_for_moe_df) == field_count

    # for each treatment field
    for _, txfield in fields_for_moe_df.iterrows():
        field_id = txfield["field_id"]

        # check that the field label matches the field name
        assert f"Field{txfield['field_label']}" == txfield["field_name"]

        # check for txfield control points
        total_mu, point_results = delivery.delivery_data_sql(connection, field_id)

        assert total_mu == 100
        print(point_results)

        # iterate over the txfield results and see if they match
        current_index = 0.0
        for _, tx_point in point_results.iterrows():
            assert tx_point[0] >= current_index
            current_index = tx_point[0]
