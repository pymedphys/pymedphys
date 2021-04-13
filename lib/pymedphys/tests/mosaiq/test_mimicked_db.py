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

import pymedphys
from pymedphys._mosaiq import helpers

from . import _connect
from .data import mimics

PATIENT_ID = 989898
FIELD_ID = 88043
A_TREATMENT_TIME = "2020-04-27 08:03:28.513"
MACHINE_ID = "2619"


@pytest.fixture(name="create_mimic_db_with_tables")
def create_mimic_db_with_tables_base():
    """ will create the test database, if it does not already exist on the instance """
    mimics.create_db_with_tables()


@pytest.fixture(name="trf_filepath")
def streamlit_e2e_testing_data_base():
    data_paths = pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip")
    date = A_TREATMENT_TIME.split(" ")[0]

    filtered_paths = [
        path
        for path in data_paths
        if date in str(path) and str(FIELD_ID) in str(path) and path.suffix == ".trf"
    ]

    return filtered_paths[0]


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


@pytest.mark.mosaiqdb
def test_get_treatments(
    create_mimic_db_with_tables,
):  # pylint: disable = unused-argument

    dt = np.timedelta64(4, "h")
    start = np.datetime64(A_TREATMENT_TIME) - dt
    end = np.datetime64(A_TREATMENT_TIME) + dt

    with _connect.connect(database=mimics.DATABASE) as connection:
        treatments = helpers.get_treatments(connection, start, end, MACHINE_ID)
        assert np.datetime64(A_TREATMENT_TIME) in treatments["start"].tolist()


@pytest.mark.mosaiqdb
def test_delivery_from_mosaiq(
    create_mimic_db_with_tables, trf_filepath
):  # pylint: disable = unused-argument
    trf_delivery = pymedphys.Delivery.from_trf(trf_filepath)

    with _connect.connect(database=mimics.DATABASE) as connection:
        mosaiq_delivery = pymedphys.Delivery.from_mosaiq(connection, FIELD_ID)

    assert np.abs(trf_delivery.mu[-1] - mosaiq_delivery.mu[-1]) < 0.2

    trf_metersetmap = trf_delivery.metersetmap(grid_resolution=5)
    mosaiq_metersetmap = mosaiq_delivery.metersetmap(grid_resolution=5)

    max_deviation = np.max(np.abs(trf_metersetmap - mosaiq_metersetmap))
    assert max_deviation < 3
