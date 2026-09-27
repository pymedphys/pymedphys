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

"""Where the DICOM listener stores what it receives, and how send reports failure.

The listener builds its storage path from values in the received dataset, so
those values must never place a file outside the storage directory.
"""

import pathlib
import types

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.connect import listen, send

SAFE_UIDS = {
    "StudyInstanceUID": "1.2.826.0.1.3680043.8.498.1",
    "SeriesInstanceUID": "1.2.826.0.1.3680043.8.498.2",
    "SOPInstanceUID": "1.2.826.0.1.3680043.8.498.3",
}


def _dataset(**overrides):
    ds = pydicom.Dataset()
    ds.PatientID = "PMP-001"
    ds.SOPClassUID = pydicom.uid.UID("1.2.840.10008.5.1.4.1.1.481.5")  # RT Plan
    for keyword, value in SAFE_UIDS.items():
        setattr(ds, keyword, value)
    for keyword, value in overrides.items():
        setattr(ds, keyword, value)
    return ds


def _store(storage: pathlib.Path, ds) -> pathlib.Path:
    listener = listen.DicomListener(storage_directory=storage)
    event = types.SimpleNamespace(
        dataset=ds,
        context=types.SimpleNamespace(
            transfer_syntax=pydicom.uid.ImplicitVRLittleEndian
        ),
    )
    status = listener.on_c_store(event)
    assert status.Status == 0x0000
    (stored,) = [path for path in storage.rglob("*") if path.is_file()]
    return stored


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def test_ordinary_values_keep_the_patient_study_series_layout(tmp_path):
    ds = _dataset()

    stored = _store(tmp_path / "store", ds)

    assert stored == (
        tmp_path
        / "store"
        / ds.PatientID
        / ds.StudyInstanceUID
        / ds.SeriesInstanceUID
        / f"RP.{ds.SOPInstanceUID}.dcm"
    )


# The storage directory sits three levels inside tmp_path, so that a
# regression writes its escaped files inside tmp_path rather than elsewhere.
def _storage(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "a" / "b" / "store"


@pytest.mark.parametrize(
    "patient_id",
    [
        "../../escaped",
        "..",
        ".",
        "ABSOLUTE",  # replaced by an absolute path inside tmp_path
        "C:\\windows",
        "a/../../b",
        "..\\..\\escaped",
    ],
)
def test_patient_id_cannot_leave_the_storage_directory(tmp_path, patient_id):
    storage = _storage(tmp_path)
    if patient_id == "ABSOLUTE":
        patient_id = str(tmp_path / "absolute")

    stored = _store(storage, _dataset(PatientID=patient_id))

    assert _inside(stored, storage)
    assert stored.relative_to(storage).parts[0] not in ("", ".", "..")
    assert len(stored.relative_to(storage).parts) == 4


@pytest.mark.parametrize(
    "keyword", ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"]
)
def test_uids_cannot_leave_the_storage_directory(tmp_path, keyword):
    storage = _storage(tmp_path)

    stored = _store(storage, _dataset(**{keyword: "../../escaped"}))

    assert _inside(stored, storage)
    assert len(stored.relative_to(storage).parts) == 4
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert [path for path in files if not _inside(path, storage)] == []


def test_different_patients_never_share_a_directory():
    # Replacing characters alone would map both of these to "A_B".
    first = listen.hierarchical_dicom_storage_directory(
        pathlib.Path("store"), _dataset(PatientID="A/B")
    )
    second = listen.hierarchical_dicom_storage_directory(
        pathlib.Path("store"), _dataset(PatientID="A_B")
    )

    assert first.parts[1] != second.parts[1]


@pytest.mark.parametrize("patient_id", ["", "   ", "CON", "nul", "COM1.txt", "LPT9"])
def test_empty_and_reserved_names_become_usable_directories(patient_id):
    directory = listen.hierarchical_dicom_storage_directory(
        pathlib.Path("store"), _dataset(PatientID=patient_id)
    )

    component = directory.parts[1]
    assert component.strip(". ")
    assert component.split(".")[0].upper() not in {"CON", "NUL", "COM1", "LPT9"}


def _status(value):
    status = pydicom.Dataset()
    status.Status = value
    return status


@pytest.fixture(name="send_args")
def fixture_send_args(tmp_path):
    path = tmp_path / "plan.dcm"
    ds = _dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
    ds.save_as(path, enforce_file_format=True)
    return types.SimpleNamespace(
        host="127.0.0.1", port=104, aetitle="PYMEDPHYS", dcmfiles=[str(path)]
    )


def _patch_sender(monkeypatch, *, verify=True, statuses=()):
    monkeypatch.setattr(send.DicomSender, "verify", lambda self: verify)
    monkeypatch.setattr(send.DicomSender, "send", lambda self, files: list(statuses))


@pytest.mark.parametrize("status", [0x0000, 0xB000, 0xB007])
def test_send_cli_succeeds_on_success_and_warning_statuses(
    monkeypatch, send_args, status
):
    _patch_sender(monkeypatch, statuses=[_status(status)])

    send.send_cli(send_args)


@pytest.mark.parametrize(
    "statuses",
    [
        [_status(0xA700)],  # out of resources
        [_status(0xC000)],  # cannot understand
        [pydicom.Dataset()],  # no response: the association was lost
        [],  # no association
    ],
)
def test_send_cli_exits_non_zero_when_a_file_is_not_stored(
    monkeypatch, send_args, statuses
):
    _patch_sender(monkeypatch, statuses=statuses)

    with pytest.raises(SystemExit) as exit_info:
        send.send_cli(send_args)

    assert exit_info.value.code == 1


def test_send_cli_exits_non_zero_when_the_host_is_unreachable(monkeypatch, send_args):
    _patch_sender(monkeypatch, verify=False)

    with pytest.raises(SystemExit) as exit_info:
        send.send_cli(send_args)

    assert exit_info.value.code == 1


def test_send_cli_exits_non_zero_for_a_file_that_is_not_dicom(
    monkeypatch, send_args, tmp_path
):
    not_dicom = tmp_path / "notes.txt"
    not_dicom.write_text("not DICOM", encoding="utf-8")
    send_args.dcmfiles = [str(not_dicom)]
    _patch_sender(monkeypatch)

    with pytest.raises(SystemExit) as exit_info:
        send.send_cli(send_args)

    assert exit_info.value.code == 1
