# Copyright (C) 2021 Cancer Care Associates

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
from .data import mimics, mocks

PATIENT_ID = 989898
FIELD_ID = 88043


@pytest.fixture(name="create_mimic_db_with_tables")
def create_mimic_db_with_tables_base():
    """ will create the test database, if it does not already exist on the instance """
    mimics.create_db_with_tables()


@pytest.mark.mosaiqdb
def test_get_patient_name(
    create_mimic_db_with_tables,
):  # pylint: disable = unused-argument

    with _connect.connect(database=mimics.DATABASE) as connection:
        name = helpers.get_patient_name(connection, PATIENT_ID)
        assert name == "PHYSICS, Mock"


@pytest.mark.mosaiqdb
def test_get_patient_fields(
    create_mimic_db_with_tables,
):  # pylint: disable = unused-argument

    with _connect.connect(database=mimics.DATABASE) as connection:
        tx_fields = helpers.get_patient_fields(connection, PATIENT_ID)
        field_id = tx_fields["field_id"].iloc[0]
        assert field_id == FIELD_ID
