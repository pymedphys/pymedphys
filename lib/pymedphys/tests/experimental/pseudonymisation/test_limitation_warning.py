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

"""Experimental pseudonymisation warns about its security limitations.

The warning discloses known limitations; it is not a deprecation and makes no
removal promise, because no replacement is available yet (decision D-019).
The public functions warn, the command prints a notice on stderr, and the
private implementation that the public functions share stays silent so that
one call produces one warning. ``pseudonymise`` also keeps Patient's Sex, as
its docstring has always stated.
"""

import pickle
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._experimental import pseudonymisation as private_pseudonymisation
from pymedphys.cli import define_parser
from pymedphys.experimental import pseudonymisation

RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
BACKGROUND_PAGE = "users/background/dicom-deidentification.html"


def _dataset():
    ds = pydicom.Dataset()
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "123456"
    ds.PatientSex = "F"
    ds.SOPClassUID = RT_PLAN_STORAGE
    ds.SOPInstanceUID = "1.2.826.0.1.3680043.10.1234.5"
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.10.1234.6"
    return ds


def _write_file(path):
    ds = _dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    pydicom.dcmwrite(path, ds, enforce_file_format=True)
    return path


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda: pseudonymisation.pseudonymise(_dataset()), id="pseudonymise"
        ),
        pytest.param(
            pseudonymisation.get_default_pseudonymisation_keywords,
            id="get_default_pseudonymisation_keywords",
        ),
        pytest.param(
            pseudonymisation.is_valid_strategy_for_keywords,
            id="is_valid_strategy_for_keywords",
        ),
    ],
)
def test_public_functions_warn_once_and_point_to_background(call):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()

    ours = [
        w
        for w in caught
        if issubclass(w.category, pseudonymisation.PseudonymisationLimitationWarning)
    ]
    assert len(ours) == 1
    message = str(ours[0].message)
    assert "without a secret key" in message
    assert BACKGROUND_PAGE in message
    assert "deprecated" not in message
    assert "removed" not in message
    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]


@pytest.mark.parametrize(
    "name",
    [
        "pseudonymise",
        "get_default_pseudonymisation_keywords",
        "is_valid_strategy_for_keywords",
    ],
)
def test_public_functions_can_be_pickled(name):
    """Pickle finds each warning wrapper by its public import path.

    Process pools pickle functions by reference, so wrapping must not make the
    public name resolve to a different object.
    """
    func = getattr(pseudonymisation, name)

    assert pickle.loads(pickle.dumps(func)) is func


@pytest.mark.pydicom
def test_private_implementation_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        private_pseudonymisation.pseudonymise(_dataset())
        private_pseudonymisation.get_default_pseudonymisation_keywords()
        private_pseudonymisation.is_valid_strategy_for_keywords()

    assert not [w for w in caught if BACKGROUND_PAGE in str(w.message)]


@pytest.mark.pydicom
def test_pseudonymise_leaves_patient_sex_unchanged():
    with pytest.warns(pseudonymisation.PseudonymisationLimitationWarning):
        pseudonymised = pseudonymisation.pseudonymise(_dataset())

    assert pseudonymised.PatientSex == "F"
    assert pseudonymised.PatientID != "123456"


@pytest.mark.pydicom
def test_cli_prints_limitation_notice_on_stderr(tmp_path, capsys):
    input_path = _write_file(tmp_path / "input.dcm")
    args = define_parser().parse_args(
        [
            "experimental",
            "dicom",
            "pseudonymise",
            str(input_path),
            "-o",
            str(tmp_path / "output" / "output.dcm"),
            "-u",
        ]
    )

    args.func(args)

    captured = capsys.readouterr()
    assert "without a secret key" in captured.err
    assert BACKGROUND_PAGE in captured.err
    assert "deprecated" not in captured.err
    assert "without a secret key" not in captured.out
