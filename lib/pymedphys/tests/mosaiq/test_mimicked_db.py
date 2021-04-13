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


from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._mosaiq import helpers

from . import _connect
from .data import mimics

PATIENT_ID = 989898
FIELD_ID = 88043
A_TREATMENT_TIME = "2020-04-27 08:03:28.513"


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


@pytest.mark.mosaiqdb
def test_get_treatment_times(
    create_mimic_db_with_tables,
):  # pylint: disable = unused-argument

    with _connect.connect(database=mimics.DATABASE) as connection:
        treatment_times = helpers.get_treatment_times(connection, FIELD_ID)
        assert np.datetime64(A_TREATMENT_TIME) in treatment_times["start"].tolist()
