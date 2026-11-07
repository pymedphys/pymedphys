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

"""The release report counts what D wrote in place of each ICC Profile (D-021)."""

import dataclasses
import enum
import json

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    instance_transform,
    release_report,
    run_report,
)
from pymedphys._dicom.deidentify.edits import Edit, EditKind
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.icc_cleaning import Refusal
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.run_qc import IccProfileMaterial

PATH = ElementPath((), "(0028,2000)")


class _Status(enum.Enum):
    RELEASED = "released"
    HELD = "held-for-review"
    SEQUESTERED = "sequestered"


@dataclasses.dataclass
class _Outcome:
    position: int
    status: _Status
    duplicate_of: int | None = None


def _report(counts):
    return release_report.release_report(
        compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        icc_profiles=counts,
    )


@pytest.mark.deid_requirement("MIDI-BP-14", "MIDI-BP-18")
def test_the_report_counts_cleaned_and_replaced_profiles_by_reason():
    report = _report(
        release_report.IccProfileCounts(
            cleaned=4, replaced={Refusal.VERSION: 1, Refusal.DEVICE_CLASS: 2}
        )
    )

    document = json.loads(release_report.to_json(report))

    assert document["icc_profiles"] == {
        "cleaned": 4,
        "replaced": [
            {"reason": "device-class", "count": 2},
            {"reason": "version", "count": 1},
        ],
    }
    # The reviewers' sections come first: descriptors, then annotations.
    sections = list(document)
    assert sections.index("icc_profiles") == sections.index("annotations") + 1
    assert sections.index("annotations") == sections.index("descriptors") + 1


def test_a_report_without_icc_profiles_counts_none():
    document = json.loads(release_report.to_json(_report(None)))

    assert document["icc_profiles"] == {"cleaned": 0, "replaced": []}
    assert "Cleaned source profiles: `0`." in to_markdown(
        release_report.to_json(_report(None))
    )


def test_every_refusal_is_a_reason_the_report_takes():
    counts = release_report.IccProfileCounts(replaced=dict.fromkeys(Refusal, 1))

    document = json.loads(release_report.to_json(_report(counts)))

    assert [entry["reason"] for entry in document["icc_profiles"]["replaced"]] == (
        sorted(refusal.value for refusal in Refusal)
    )


@pytest.mark.parametrize(
    "counts, field",
    [
        (release_report.IccProfileCounts(cleaned=-1), "icc_profiles cleaned"),
        (release_report.IccProfileCounts(cleaned=1.0), "icc_profiles cleaned"),
        (release_report.IccProfileCounts(cleaned=True), "icc_profiles cleaned"),
        (
            release_report.IccProfileCounts(replaced={Refusal.VERSION: -1}),
            "icc_profiles reason count",
        ),
        (
            release_report.IccProfileCounts(replaced={"version": 1}),
            "icc_profiles reason",
        ),
        (
            release_report.IccProfileCounts(replaced={Refusal.VERSION: True}),
            "icc_profiles reason count",
        ),
        ({"cleaned": 1}, "icc_profiles"),
    ],
)
def test_the_report_refuses_icc_profile_counts_of_another_form(counts, field):
    with pytest.raises(release_report.ReleaseReportError, match=field):
        release_report.to_json(_report(counts))


def test_the_run_counts_released_and_held_instances_once_each():
    outcomes = [
        _Outcome(0, _Status.RELEASED),
        _Outcome(1, _Status.HELD),
        _Outcome(2, _Status.RELEASED),
        # Not written, and a copy of a counted instance.
        _Outcome(3, _Status.SEQUESTERED),
        _Outcome(4, _Status.RELEASED, duplicate_of=0),
    ]
    material = {
        0: (IccProfileMaterial(PATH, None),),
        1: (IccProfileMaterial(PATH, Refusal.TAG_DATA),),
        2: (IccProfileMaterial(PATH, Refusal.TAG_DATA),),
        3: (IccProfileMaterial(PATH, None),),
        4: (IccProfileMaterial(PATH, None),),
    }

    counts = run_report.icc_profile_counts(outcomes, material)

    assert counts == release_report.IccProfileCounts(
        cleaned=1, replaced={Refusal.TAG_DATA: 2}
    )
    assert dict(counts.replaced) == {Refusal.TAG_DATA: 2}


def test_material_lists_each_replaced_icc_profile_with_its_refusal():
    other = ElementPath((), "(0008,103E)")
    edits = instance_transform.InstanceEdits(
        edits=(
            Edit(other, "D", EditKind.REPLACE, ("DEIDENTIFIED",)),
            Edit(PATH, "D", EditKind.REPLACE, (b"",), icc_refusal=Refusal.VERSION),
        ),
        source_values=(),
        not_collected=(),
        sequestrations=(),
    )
    removed = instance_transform.InstanceEdits(
        edits=(Edit(PATH, "X", EditKind.REMOVE),),
        source_values=(),
        not_collected=(),
        sequestrations=(),
    )

    assert instance_transform.icc_profiles_of(edits) == (
        IccProfileMaterial(PATH, Refusal.VERSION),
    )
    assert not instance_transform.icc_profiles_of(removed)
