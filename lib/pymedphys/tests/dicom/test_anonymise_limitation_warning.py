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

"""``pymedphys.dicom.anonymise`` warns about its limitations (decision D-019).

The warning discloses known limitations; it is not a deprecation and makes no
removal promise. The public function warns, the command prints a notice on
standard error, and the private implementation, which experimental
pseudonymisation also uses, stays silent.
"""

import pickle
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys import dicom
from pymedphys._dicom.anonymise import anonymise_dataset as private_anonymise
from pymedphys.cli import define_parser
from pymedphys.experimental import pseudonymisation

RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
BACKGROUND_PAGE = "users/background/dicom-deidentification.html"


def _dataset():
    ds = pydicom.Dataset()
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "123456"
    ds.SOPClassUID = RT_PLAN_STORAGE
    ds.SOPInstanceUID = "1.2.826.0.1.3680043.10.1234.5"
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.10.1234.6"
    ds.Modality = "RTPLAN"
    return ds


def _limitation_warnings(caught):
    return [
        w
        for w in caught
        if issubclass(w.category, dicom.AnonymisationLimitationWarning)
    ]


@pytest.mark.pydicom
def test_public_anonymise_warns_once_and_points_to_background():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dicom.anonymise(_dataset())

    ours = _limitation_warnings(caught)
    assert len(ours) == 1
    assert issubclass(ours[0].category, UserWarning)
    message = str(ours[0].message)
    assert "UID" in message
    assert BACKGROUND_PAGE in message
    assert "deprecat" not in message.lower()
    assert "remove" not in message.lower()
    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]


@pytest.mark.pydicom
def test_private_anonymise_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        private_anonymise(_dataset())

    assert not _limitation_warnings(caught)


@pytest.mark.pydicom
def test_pseudonymise_emits_only_its_own_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pseudonymisation.pseudonymise(_dataset())

    assert not _limitation_warnings(caught)
    assert [
        w
        for w in caught
        if issubclass(w.category, pseudonymisation.PseudonymisationLimitationWarning)
    ]


def test_public_anonymise_can_be_pickled():
    """Pickle finds the warning wrapper by its public import path."""
    assert pickle.loads(pickle.dumps(dicom.anonymise)) is dicom.anonymise


@pytest.mark.pydicom
def test_cli_prints_limitation_notice_on_stderr(tmp_path, capsys):
    ds = _dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    input_path = tmp_path / "input.dcm"
    pydicom.dcmwrite(input_path, ds, enforce_file_format=True)

    args = define_parser().parse_args(
        [
            "dicom",
            "anonymise",
            str(input_path),
            "-o",
            str(tmp_path / "output" / "output.dcm"),
            "-u",
        ]
    )
    args.func(args)

    captured = capsys.readouterr()
    assert BACKGROUND_PAGE in captured.err
    assert "UID" in captured.err
    assert "deprecat" not in captured.err.lower()
    assert BACKGROUND_PAGE not in captured.out
    assert "Wrote 1 file(s)" in captured.out
