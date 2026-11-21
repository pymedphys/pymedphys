# Copyright (C) 2026 jdotc1
# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import lzma
from types import SimpleNamespace

from pymedphys._icom import patients

IP = "192.168.100.200"
START = "2026-09-28T10:00:00"


def _icom_item(index, patient_id=None, patient_name=None):
    """Return a minimal iCOM data item.

    It holds a timestamp, the item's index in the stream, and optionally the
    Patient ID and Patient Name fields. It is not a delivery that pymedphys
    can read, so the archiver keeps it under ``unknown_error_in_record``, in a
    folder named after the patient.
    """
    item = b"\x00" * 8 + b"2026-09-2810:00:00" + bytes([index])
    if patient_id is not None:
        item += b"0 \x00LO\x00P\x07\x00\x00\x00" + patient_id.encode() + b"\x00"
    if patient_name is not None:
        item += b"0\x10\x00PN\x00P\x07\x00\x00\x00" + patient_name.encode() + b"\x00"
    return item


def test_patient_folder_name_is_valid_on_windows(tmp_path):
    """A double quote in a patient's name, which Windows does not allow in
    folder names, is encoded in the name of the patient's archive folder."""
    item = _icom_item(0, patient_id="123456", patient_name='SMITH, JOHN "JACK"')

    patients.save_patient_data(START, [item], tmp_path)

    (archive,) = tmp_path.rglob("*.xz")
    assert archive.parent.name == "123456_SMITH, JOHN %22JACK%22"
    with lzma.open(archive) as f:
        assert f.read() == item


def test_a_delivery_that_cannot_be_archived_does_not_stop_recording(tmp_path, caplog):
    # A file where the archive folder should be makes archiving fail.
    patients_dir = tmp_path / "patients"
    patients_dir.write_text("")
    patient_icom_data = patients.PatientIcomData(patients_dir)

    patient_icom_data.update_data(
        IP, _icom_item(0, patient_id="123456", patient_name="SMITH")
    )
    with caplog.at_level(logging.ERROR):
        patient_icom_data.update_data(IP, _icom_item(1))

    assert f"Could not archive the delivery that started at {START}." in caplog.text

    # The next delivery is recorded and archived on its own.
    patients_dir.unlink()
    patients_dir.mkdir()
    next_delivery = _icom_item(2, patient_id="654321", patient_name="JONES")
    patient_icom_data.update_data(IP, next_delivery)
    patient_icom_data.update_data(IP, _icom_item(3))

    (archive,) = patients_dir.rglob("*.xz")
    assert archive.parent.name == "654321_JONES"
    with lzma.open(archive) as f:
        assert f.read() == next_delivery


def test_icom_restricted_archive_logs_do_not_include_patient_identifiers(
    tmp_path, caplog
):
    """Opt-in restricted logging excludes patient-bearing archive details."""
    patient_id, patient_name = "738419", "SYNTHETIC, PATIENT"
    item = _icom_item(0, patient_id=patient_id, patient_name=patient_name)

    with caplog.at_level(logging.DEBUG):
        patients.save_patient_data(START, [item], tmp_path, restricted_logs=True)

    (archive,) = tmp_path.rglob("*.xz")
    assert archive.exists()
    assert patient_id not in caplog.text
    assert patient_name not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_icom_restricted_acquisition_logs_do_not_include_patient_identifiers(
    tmp_path, caplog
):
    """Restricted acquisition progress omits delivery context."""
    patient_id, patient_name = "738419", "SYNTHETIC, PATIENT"
    recorder = patients.PatientIcomData(tmp_path, restricted_logs=True)
    with caplog.at_level(logging.DEBUG):
        recorder.update_data(
            IP, _icom_item(0, patient_id=patient_id, patient_name=patient_name)
        )
        recorder.update_data(IP, _icom_item(1))

    assert "iCOM acquisition data received" in caplog.text
    assert patient_id not in caplog.text
    assert patient_name not in caplog.text
    assert START not in caplog.text
    assert IP not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_icom_default_archive_logs_preserve_operator_details(
    tmp_path, caplog, monkeypatch
):
    """Protected-local logs retain patient, archive path and delivery MU."""
    patient_id, patient_name = "738419", "SYNTHETIC, PATIENT"
    item = _icom_item(0, patient_id=patient_id, patient_name=patient_name)
    monkeypatch.setattr(
        patients, "validate_data", lambda _data: SimpleNamespace(mu=[123.4])
    )

    with caplog.at_level(logging.DEBUG):
        patients.save_patient_data(START, [item], tmp_path)

    assert patient_id in caplog.text
    assert patient_name in caplog.text
    assert str(tmp_path) in caplog.text
    assert "123.4" in caplog.text
    (archive,) = tmp_path.rglob("*.xz")
    with lzma.open(archive) as f:
        assert f.read() == item


def test_icom_default_acquisition_logs_preserve_operator_details(tmp_path, caplog):
    """Protected-local acquisition logs retain source and start timestamp."""
    patient_id, patient_name = "738419", "SYNTHETIC, PATIENT"
    recorder = patients.PatientIcomData(tmp_path)

    with caplog.at_level(logging.DEBUG):
        recorder.update_data(
            IP, _icom_item(0, patient_id=patient_id, patient_name=patient_name)
        )

    assert patient_id in caplog.text
    assert patient_name in caplog.text
    assert IP in caplog.text
    assert "2026-09-2810:00:00" in caplog.text
    assert recorder._usage_start[IP] == START


def test_icom_restricted_archive_failure_omits_delivery_context(tmp_path, caplog):
    """Archive failures remain visible without patient-named paths."""
    blocked_directory = tmp_path / "patients"
    blocked_directory.write_text("")
    recorder = patients.PatientIcomData(blocked_directory, restricted_logs=True)
    with caplog.at_level(logging.DEBUG):
        recorder.update_data(
            IP, _icom_item(0, patient_id="738419", patient_name="SYNTHETIC, PATIENT")
        )
        recorder.update_data(IP, _icom_item(1))

    assert "Could not archive iCOM delivery" in caplog.text
    for sensitive in ("738419", "SYNTHETIC, PATIENT", IP, START, str(tmp_path)):
        assert sensitive not in caplog.text
