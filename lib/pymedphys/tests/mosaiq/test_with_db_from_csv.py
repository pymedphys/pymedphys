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


import csv
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._mosaiq import helpers
from pymedphys._mosaiq.mock import from_csv, utilities

MOCK_DATA_DIRECTORY = pathlib.Path(from_csv.__file__).parent / "data"

PATIENT_ID = 989898
FIELD_ID = 88043
A_TREATMENT_DATETIME = "2020-04-27 08:03:28.513"
A_TRF_FILENAME = "20_04_26 22_03_30 Z 1-1_3ABUT.trf"
MACHINE_ID = "2619"
FIELD_NAME = "3ABUT"
TIMEZONE = "Australia/Sydney"
FIRST_NAME = "MOCK"
LAST_NAME = "PHYSICS"
FULL_NAME = f"{LAST_NAME}, {FIRST_NAME.capitalize()}"
QCL_LOCATION = "Physics_Check"
AN_UNCOMPLETED_QCL_DUE_DATETIME = "2021-05-21 23:59:59"
QCL_COMPLETED_DATETIMES = ["2021-04-14 09:11:30.387", "2021-04-14 09:11:35.383"]


# Loading the mimic tables takes seconds per call. The connection is read-only,
# so no test can change them, and they are loaded once for the module.
@pytest.fixture(name="connection", scope="module")
def connection_base():
    """Load the mimic tables into the test database, then connect to it."""
    from_csv.create_db_with_tables_from_csv()
    with utilities.connect(database=from_csv.DATABASE_NAME) as connection:
        yield connection


@pytest.fixture(name="trf_filepath")
def trf_filepath_base():
    data_paths = pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip")
    filtered_paths = [path for path in data_paths if path.name == A_TRF_FILENAME]
    assert len(filtered_paths) == 1

    return filtered_paths[0]


@pytest.fixture(name="dicom_filepath")
def dicom_filepath_base():
    data_paths = pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip")
    filtered_paths = [
        path for path in data_paths if path.name == f"{PATIENT_ID}_{FIELD_NAME}.dcm"
    ]
    assert len(filtered_paths) == 1

    return filtered_paths[0]


@pytest.mark.mosaiqdb
def test_get_patient_name(connection):
    name = helpers.get_patient_name(connection, PATIENT_ID)
    assert name == FULL_NAME


@pytest.mark.mosaiqdb
def test_get_patient_fields(connection):
    tx_fields = helpers.get_patient_fields(connection, PATIENT_ID)
    field_id = tx_fields["field_id"].iloc[0]
    assert field_id == FIELD_ID


@pytest.mark.mosaiqdb
def test_get_treatment_times(connection):
    treatment_times = helpers.get_treatment_times(connection, FIELD_ID)
    assert np.datetime64(A_TREATMENT_DATETIME) in treatment_times["start"].tolist()


@pytest.mark.mosaiqdb
def test_get_treatments(connection):
    time_delta = np.timedelta64(4, "h")
    start = np.datetime64(A_TREATMENT_DATETIME) - time_delta
    end = np.datetime64(A_TREATMENT_DATETIME) + time_delta

    treatments = helpers.get_treatments(connection, start, end, MACHINE_ID)
    assert (
        np.datetime64(A_TREATMENT_DATETIME) in treatments["start"].tolist()  # pylint: disable=unsubscriptable-object
    )


@pytest.mark.mosaiqdb
def test_delivery_from_mosaiq_matches_the_field_record(connection):
    # Needs only the mosaiq extra, unlike the comparison with DICOM and TRF
    # below. The expected values come from the CSV the test database is loaded
    # from, not through the database.
    field = _csv_rows("TxField.csv", FIELD_ID)[0]
    points = sorted(
        _csv_rows("TxFieldPoint.csv", FIELD_ID), key=lambda row: int(row["Point"])
    )
    index = np.array([float(row["Index"]) for row in points])
    meterset = float(field["Meterset"])

    delivery = pymedphys.Delivery.from_mosaiq(connection, FIELD_ID)

    assert np.shape(delivery.mlc) == (len(points), 80, 2)
    assert np.shape(delivery.jaw) == (len(points), 2)
    assert delivery.mu[0] == 0
    assert delivery.mu[-1] == pytest.approx(meterset)
    assert np.all(np.diff(delivery.mu) >= 0)
    # The test database stores Index as DECIMAL with no decimal places, so
    # 33.333 becomes 33, which moves the MU by up to half a percent of Index.
    np.testing.assert_allclose(delivery.mu, index / index[-1] * meterset, atol=1)
    # Angles are returned in the range -180 to 180 degrees.
    for angles, column in [
        (delivery.gantry, "Gantry_Ang"),
        (delivery.collimator, "Coll_Ang"),
    ]:
        np.testing.assert_allclose(
            np.mod(angles, 360), [float(row[column]) % 360 for row in points]
        )
    # The Y jaws, in mm, as positive distances from the central axis.
    np.testing.assert_allclose(
        delivery.jaw,
        [[10 * float(row["Coll_Y2"]), -10 * float(row["Coll_Y1"])] for row in points],
    )

    # The field, 3ABUT, is three abutting 60 mm segments, each delivered
    # between a pair of control points. Leaf pairs 14 to 65 lie within the
    # jaws; every one is open 60 mm, centred 60 mm to one side, then on the
    # central axis, then 60 mm to the other side.
    mlc = np.array(delivery.mlc)[:, 14:66, :]
    np.testing.assert_allclose(mlc.sum(axis=-1), 60)
    np.testing.assert_allclose(
        (mlc[..., 0] - mlc[..., 1]) / 2,
        np.broadcast_to([[-60], [-60], [0], [0], [60], [60]], mlc.shape[:2]),
    )


def _csv_rows(table, field_id):
    path = MOCK_DATA_DIRECTORY / table
    with open(path, newline="", encoding="utf-8") as csv_file:
        return [
            row for row in csv.DictReader(csv_file) if int(row["FLD_ID"]) == field_id
        ]


@pytest.mark.mosaiqdb
def test_delivery_from_mosaiq(connection, trf_filepath, dicom_filepath):
    pytest.importorskip("pydicom")  # from the dicom extra, not mosaiq
    trf_delivery = pymedphys.Delivery.from_trf(trf_filepath)
    dicom_delivery = pymedphys.Delivery.from_dicom(dicom_filepath)
    mosaiq_delivery = pymedphys.Delivery.from_mosaiq(connection, FIELD_ID)

    assert np.allclose(dicom_delivery.mu, mosaiq_delivery.mu, atol=1)
    assert np.allclose(dicom_delivery.mlc, mosaiq_delivery.mlc, atol=0.1)
    assert np.allclose(dicom_delivery.jaw, mosaiq_delivery.jaw, atol=0.1)
    assert np.allclose(dicom_delivery.gantry, mosaiq_delivery.gantry, atol=0.1)
    assert np.allclose(dicom_delivery.collimator, mosaiq_delivery.collimator, atol=0.1)

    assert np.abs(trf_delivery.mu[-1] - mosaiq_delivery.mu[-1]) < 0.2
    trf_metersetmap = trf_delivery.metersetmap(grid_resolution=5)
    mosaiq_metersetmap = mosaiq_delivery.metersetmap(grid_resolution=5)

    max_deviation = np.max(np.abs(trf_metersetmap - mosaiq_metersetmap))
    assert max_deviation < 3


@pytest.mark.mosaiqdb
def test_trf_identification(connection: pymedphys.mosaiq.Connection, trf_filepath):
    pytest.importorskip("attr")  # identification needs "pymedphys[trf,mosaiq]"
    delivery_details = pymedphys.trf.identify(connection, trf_filepath, TIMEZONE)
    assert delivery_details.field_id == FIELD_ID
    assert str(delivery_details.first_name).lower() == FIRST_NAME.lower()
    assert str(delivery_details.last_name).lower() == LAST_NAME.lower()
    assert delivery_details.patient_id == str(PATIENT_ID)


@pytest.mark.mosaiqdb
def test_get_incomplete_qcls(connection: pymedphys.mosaiq.Connection):
    incomplete_qcls = helpers.get_incomplete_qcls(connection, QCL_LOCATION)
    assert (
        np.datetime64(AN_UNCOMPLETED_QCL_DUE_DATETIME)
        in incomplete_qcls["due"].tolist()  # pylint: disable=unsubscriptable-object
    )


@pytest.mark.mosaiqdb
def test_get_qcls_by_date(connection: pymedphys.mosaiq.Connection):
    a_completion_datetime = QCL_COMPLETED_DATETIMES[0]

    large_time_delta = np.timedelta64(90, "D")
    start = np.datetime64(a_completion_datetime) - large_time_delta
    end = np.datetime64(a_completion_datetime) + large_time_delta
    qcls_by_date = helpers.get_qcls_by_date(connection, QCL_LOCATION, start, end)
    assert (
        np.datetime64(AN_UNCOMPLETED_QCL_DUE_DATETIME)
        # pylint: disable=unsubscriptable-object
        not in qcls_by_date["due"].tolist()
    )
    for dt in QCL_COMPLETED_DATETIMES:
        assert (
            np.datetime64(dt)
            # pylint: disable=unsubscriptable-object
            in qcls_by_date["actual_completed_time"].tolist()
        )

    small_time_delta = np.timedelta64(3, "s")
    start = np.datetime64(a_completion_datetime) - small_time_delta
    end = np.datetime64(a_completion_datetime) + small_time_delta
    qcls_by_date = helpers.get_qcls_by_date(connection, QCL_LOCATION, start, end)

    assert (
        np.datetime64(a_completion_datetime)
        # pylint: disable=unsubscriptable-object
        in qcls_by_date["actual_completed_time"].tolist()
    )
    for dt in list(set(QCL_COMPLETED_DATETIMES).difference({a_completion_datetime})):
        # pylint: disable=unsubscriptable-object
        assert np.datetime64(dt) not in qcls_by_date["actual_completed_time"].tolist()
