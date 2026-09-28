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
