# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Release sender associations even when local validation or DIMSE calls fail."""

from types import SimpleNamespace

from pymedphys._imports import pytest

from pymedphys._dicom.connect import send


class Dataset:
    SOPInstanceUID = "1.2.3"


@pytest.fixture
def association(monkeypatch):
    class Association:
        is_established = True

        def __init__(self):
            self.releases = 0
            self.failure = None

        def send_c_echo(self):
            if self.failure:
                raise self.failure
            return SimpleNamespace(Status=0)

        def send_c_store(self, _dataset):
            if self.failure:
                raise self.failure
            return SimpleNamespace(Status=0)

        def release(self):
            self.releases += 1

    assoc = Association()
    ae = SimpleNamespace(associate=lambda *args, **kwargs: assoc)
    monkeypatch.setattr(
        send,
        "pynetdicom",
        SimpleNamespace(
            AE=lambda **kwargs: ae,
            VerificationPresentationContexts=[],
            StoragePresentationContexts=[],
        ),
    )
    monkeypatch.setattr(
        send,
        "pydicom",
        SimpleNamespace(
            Dataset=Dataset,
            uid=SimpleNamespace(ImplicitVRLittleEndian="1.2.840.10008.1.2"),
            dcmread=lambda _path: Dataset(),
        ),
    )
    return assoc


@pytest.mark.parametrize("operation", ["verify", "send"])
def test_dimse_failure_releases_established_association(association, operation):
    association.failure = RuntimeError("synthetic transport failure")
    sender = send.DicomSender()
    with pytest.raises(RuntimeError, match="synthetic transport failure"):
        if operation == "verify":
            sender.verify()
        else:
            sender.send([Dataset()])
    assert association.releases == 1


def test_invalid_local_input_releases_established_association(association):
    with pytest.raises(TypeError):
        send.DicomSender().send([object()])
    assert association.releases == 1


def test_unreadable_local_file_releases_established_association(
    association, monkeypatch
):
    def cannot_read(_path):
        raise OSError("synthetic read failure")

    monkeypatch.setattr(send.pydicom, "dcmread", cannot_read)
    with pytest.raises(OSError, match="synthetic read failure"):
        send.DicomSender().send(["synthetic.dcm"])
    assert association.releases == 1


@pytest.mark.parametrize("operation", ["verify", "send"])
def test_success_releases_association_once(association, operation):
    sender = send.DicomSender()
    if operation == "verify":
        assert sender.verify()
    else:
        assert sender.send([Dataset()])[0].Status == 0
    assert association.releases == 1
