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

"""A run collects the values of a patient's instances that are out of scope.

An instance out of scope whose IOD the pinned tables define, such as an MR
image, is planned and edited only so that its values are searched for in its
subject's released files; it is never written (D-027). Every file is
synthetic.
"""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.release_gate import Decision, ReasonCode
from pymedphys._dicom.deidentify.scope import Disposition, UnsupportedIod

from . import _synthetic_references as synthetic
from .test_deidentify_instance_transform import _source, _transform

# The run module's fixture, for a base directory short enough for Windows.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

pytestmark = pytest.mark.pydicom

_SHARED = "QUIMBYZELDA7"
_NOT_REPORTED = ReasonCode.NOT_REPORTED
_REFERRING_PHYSICIANS_NAME = 0x00080090


def _mr():
    return synthetic.instance(
        synthetic.MR_IMAGE_STORAGE, synthetic.OTHER, synthetic.OTHER_SERIES
    )


def _run(tmp_path, datasets):
    return run.run(
        _source(tmp_path, datasets),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )


def _released(tmp_path):
    release = tmp_path / "release"
    return sorted(path.name for path in release.rglob("*.dcm"))


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.3-01")
def test_an_out_of_scope_sibling_no_longer_withholds_its_subject(tmp_path):
    result = _run(tmp_path, [_mr(), synthetic.rt_dose()])

    mr, dose = result.outcomes
    assert mr.status is run.Status.SEQUESTERED
    assert mr.reasons == (UnsupportedIod("MR Image"),)
    assert dose.status is run.Status.RELEASED
    # Only the dose is written: the MR image was read for its values alone.
    assert len(_released(tmp_path)) == 1


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_value_of_an_out_of_scope_sibling_is_searched_for(tmp_path):
    mr = _mr()
    mr.InstitutionName = _SHARED  # removed (X), so collected
    dose = synthetic.rt_dose()
    dose.DoseUnits = _SHARED  # kept as it is (K)

    result = _run(tmp_path, [mr, dose])

    written = result.outcomes[1]
    assert written.status is not run.Status.RELEASED
    codes = {reason.code for reason in written.reasons}
    assert ReasonCode.RESIDUAL_TEXT in codes
    assert _NOT_REPORTED not in codes
    assert _released(tmp_path) == []


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_an_out_of_scope_sibling_whose_values_are_not_all_collected_withholds(
    tmp_path,
):
    # Outside ISO 646 with no Specific Character Set, so the name is read only
    # as bytes, and copies of it in another encoding could not be found.
    mr = _mr()
    mr[_REFERRING_PHYSICIANS_NAME] = pydicom.DataElement(
        _REFERRING_PHYSICIANS_NAME, "PN", b"Synth\xe9tic^Name"
    )

    result = _run(tmp_path, [mr, synthetic.rt_dose()])

    dose = result.outcomes[1]
    assert dose.status is run.Status.SEQUESTERED
    assert {(reason.decision, reason.code) for reason in dose.reasons} >= {
        (Decision.WITHHOLD, ReasonCode.READ_AS_LATIN_1)
    }
    assert _released(tmp_path) == []


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.3-01")
def test_an_unlisted_sop_class_still_withholds_its_subject(tmp_path):
    # No IOD of the pinned tables gives a plan by which to collect its values.
    unlisted = _mr()
    unlisted.SOPClassUID = "2.25.999"

    result = _run(tmp_path, [unlisted, synthetic.rt_dose()])

    other, dose = result.outcomes
    assert other.reasons == (Disposition.UNLISTED_SOP_CLASS,)
    assert dose.status is run.Status.SEQUESTERED
    assert _NOT_REPORTED in {reason.code for reason in dose.reasons}
