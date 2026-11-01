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

"""Residual findings whose only sources are instances that the run does not write.

An instance that the transform sequesters, such as a dose report out of
scope, is still read so that its values join its subject's residual search
(D-027). A UID that only such instances held, found in a UID that a selected
option keeps (D-042), and a standard code's meaning that only such instances
held (D-032), no longer withhold or hold the subject's written files.
"""

import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
    unwritten,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    UIDS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.reasons import HeldPixelData, PixelDataReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import (
    Exemption,
    standard_code_meanings,
)
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_descriptors import ReviewedDescriptors
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT

from . import _synthetic_dose_reports as reports
from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
STUDY = "2.25.7100"  # the study that the dose report names
STUDY_INSTANCE_UID = "(0020,000D)"
CONTENT_ITEM_UID = "(0040,A124)"
CODE_MEANING = "(0008,0104)"
DESIGNATOR = "(0008,0102)"
TEXT_VALUE = "(0040,A160)"
# A content item's UID, and a code item's meaning and designator, as a
# removed Content Sequence holds them.
CONTENT = (("(0040,A730)", 0), ("(0040,A730)", 2))
SCOPE = ElementPath(CONTENT, CONTENT_ITEM_UID)
REGION = (*CONTENT, ("(0040,A168)", 0))
MEANING = ElementPath(REGION, CODE_MEANING)
SCHEME = ElementPath(REGION, DESIGNATOR)


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("ascii")
    value += (b"\x00" if vr == "UI" else b" ") * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(*elements, meta=b""):
    """A written file holding ``elements``, given in the order of their tags."""
    syntax = _element(0x00020010, "UI", "1.2.840.10008.1.2.1")
    return bytes(128) + b"DICM" + meta + syntax + b"".join(elements)


def _instance(values, options=()):
    """The coverage of one instance that collected ``values``."""
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        options=options,
    )


def _pooled(*sequestered, written=(), options=()):
    """The pooled coverage of sequestered instances' values and a written one's.

    Each of ``sequestered`` is one instance's values, which the transform
    marks as it marks a sequestered instance's evidence.
    """
    return Coverage.merge(
        _instance(written, options),
        *(unwritten(_instance(values, options)) for values in sequestered),
    )


def _coverage(*values, written=(), options=()):
    """The pooled coverage of an unwritten instance's values and a written one's."""
    return _pooled(values, written=written, options=options)


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


# Coverage.


def test_a_value_is_unwritten_only_where_every_coverage_that_collected_it_says_so():
    shared = SourceValue(SCOPE, "UI", STUDY)
    only = SourceValue(MEANING, "LO", "Chest")
    sequestered = Coverage(
        planned=frozenset({SCOPE, MEANING}),
        collected=(shared, only),
        unwritten=frozenset({shared, only}),
    )
    written = Coverage(planned=frozenset({SCOPE}), collected=(shared,))

    assert Coverage.merge(sequestered).unwritten == {shared, only}
    assert Coverage.merge(written, sequestered).unwritten == {only}
    assert Coverage.merge(sequestered, written).unwritten == {only}
    assert not Coverage.merge(written).unwritten


def test_a_coverage_refuses_an_unwritten_value_that_it_did_not_collect():
    value = SourceValue(SCOPE, "UI", STUDY)
    with pytest.raises(ValueError):
        Coverage(planned=frozenset(), collected=(), unwritten=frozenset({value}))
    with pytest.raises(TypeError):
        Coverage(planned=frozenset(), collected=(value,), unwritten={value})
    with pytest.raises(TypeError):
        Coverage(planned=frozenset(), collected=(), unwritten=frozenset({STUDY}))
    with pytest.raises(ValueError):
        Coverage(planned=frozenset(), collected=(), coded=frozenset({value}))


def test_a_meaning_is_coded_only_where_every_coverage_that_collected_it_says_so():
    meaning = SourceValue(MEANING, "LO", "Chest")
    standard = Coverage(
        planned=frozenset({MEANING}), collected=(meaning,), coded=frozenset({meaning})
    )
    unqualified = Coverage(planned=frozenset({MEANING}), collected=(meaning,))

    assert Coverage.merge(standard).coded == {meaning}
    assert not Coverage.merge(standard, unqualified).coded
    assert not Coverage.merge(unqualified, standard).coded


def test_unwritten_evidence_gives_every_collected_value_held_or_not():
    values = (SourceValue(SCOPE, "UI", STUDY), SourceValue(MEANING, "LO", "Chest"))
    coverage = Coverage(planned=frozenset({SCOPE, MEANING}), collected=values)
    held = HeldEvidence(coverage, (HeldPixelData(PixelDataReason.NO_TEXT_FOUND),))

    assert unwritten(coverage).unwritten == frozenset(values)
    assert unwritten(held).coverage.unwritten == frozenset(values)
    assert unwritten(held).held == held.held


# The unwritten UID (D-042).


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_a_uid_from_unwritten_instances_alone_in_a_kept_uid_is_explained():
    condition = release_condition(
        _coverage(SourceValue(SCOPE, "UI", STUDY), options=(UIDS,)),
        _written(_element(0x0020000D, "UI", STUDY)),
    )

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(STUDY_INSTANCE_UID, Exemption.UNWRITTEN_UID)]
    # The finding stays in the search, for the QC pack.
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
@pytest.mark.parametrize(
    "written_values, options, found_in",
    [
        # A written instance also held it at the source, as a reference that
        # the option replaced while keeping the UID it names.
        ((SourceValue(SCOPE, "UI", STUDY),), (UIDS,), STUDY_INSTANCE_UID),
        # A written instance held another value at the same source, which
        # the search could have found there.
        ((SourceValue(SCOPE, "UI", "2.25.7999"),), (UIDS,), STUDY_INSTANCE_UID),
        # No option keeps the Study Instance UID.
        ((), (), STUDY_INSTANCE_UID),
    ],
)
def test_a_uid_that_a_written_instance_or_no_option_explains_still_withholds(
    written_values, options, found_in
):
    condition = release_condition(
        _coverage(
            SourceValue(SCOPE, "UI", STUDY), written=written_values, options=options
        ),
        _written(_element(0x0020000D, "UI", STUDY)),
    )

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted
    (reason,) = condition.reasons
    assert reason.code is ReasonCode.RESIDUAL_UID
    assert reason.location.element.tag == found_in


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
@pytest.mark.parametrize(
    "written",
    [
        # Inside a longer kept UID.
        _written(_element(0x0020000D, "UI", f"{STUDY}.5")),
        # In kept text, which no option keeps as a UID.
        _written(_element(0x00204000, "LT", f"SEE {STUDY}")),
        # In a UID that no option keeps.
        _written(_element(0x00081167, "UI", STUDY)),
        # In the File Meta Information.
        _written(meta=_element(0x00020003, "UI", STUDY)),
    ],
    ids=["longer-uid", "text", "uid-not-kept", "file-meta"],
)
def test_a_uid_from_unwritten_instances_anywhere_else_still_withholds(written):
    condition = release_condition(
        _coverage(SourceValue(SCOPE, "UI", STUDY), options=(UIDS,)), written
    )

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_UID]


# The unwritten code meaning (D-032).

SERIES_DESCRIPTION = _element(0x0008103E, "LO", "AXIAL CHEST")


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_standard_codes_meaning_from_unwritten_instances_alone_is_exempt():
    condition = release_condition(
        _coverage(
            SourceValue(MEANING, "LO", "Chest"), SourceValue(SCHEME, "SH", "SCT")
        ),
        _written(SERIES_DESCRIPTION),
    )

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [("(0008,103E)", Exemption.UNWRITTEN_CODE_MEANING)]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "values, written_values",
    [
        # A local scheme's meaning can be the site's own text.
        (
            (SourceValue(MEANING, "LO", "Chest"), SourceValue(SCHEME, "SH", "99LOCAL")),
            (),
        ),
        # No designator was collected.
        ((SourceValue(MEANING, "LO", "Chest"),), ()),
        # A written instance also held the meaning.
        (
            (SourceValue(MEANING, "LO", "Chest"), SourceValue(SCHEME, "SH", "SCT")),
            (SourceValue(MEANING, "LO", "Chest"),),
        ),
        # Free text, such as a TEXT content item's value.
        ((SourceValue(ElementPath(CONTENT, TEXT_VALUE), "UT", "Chest"),), ()),
        # A Code Meaning outside an item names no code item.
        ((SourceValue(ElementPath((), CODE_MEANING), "LO", "Chest"),), ()),
    ],
    ids=[
        "local-scheme",
        "no-designator",
        "written-meaning",
        "free-text",
        "no-item",
    ],
)
def test_other_text_from_unwritten_instances_still_goes_to_review(
    values, written_values
):
    condition = release_condition(
        _coverage(*values, written=written_values), _written(SERIES_DESCRIPTION)
    )

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]


URN_CODE = "(0008,0120)"


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "meaning", ["SYNTHETIC LABEL", "Chest"], ids=["other-meaning", "same-meaning"]
)
def test_a_meaning_is_qualified_by_its_own_item_not_another_instances(meaning):
    """Two sequestered instances hold a code item at the same place.

    One is SCT 816094009 "Chest"; the other is a URN code, whose item needs
    no Coding Scheme Designator (PS3.3 Table 8.8-1a). The pooled values hold
    SCT at the designator's place, but the URN code's meaning, whether or not
    it equals the other, must still go to review where kept text holds it.
    """
    standard = (SourceValue(MEANING, "LO", "Chest"), SourceValue(SCHEME, "SH", "SCT"))
    urn = (
        SourceValue(ElementPath(REGION, URN_CODE), "UR", "urn:oid:2.25.7999"),
        SourceValue(MEANING, "LO", meaning),
    )
    written = _written(_element(0x00081090, "LO", f"AXIAL {meaning.upper()}"))

    alone = release_condition(_pooled(urn), written)
    beside = release_condition(_pooled(standard, urn), written)
    either_order = release_condition(_pooled(urn, standard), written)

    for condition in (alone, beside, either_order):
        assert condition.decision is Decision.QC_REVIEW
        assert not condition.exempted
    # The standard code's meaning alone is still exempt.
    assert _exempted(release_condition(_pooled(standard), _written(SERIES_DESCRIPTION)))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_another_instances_local_designator_does_not_disqualify_a_standard_meaning():
    # A written instance's own code item at the same place is local, but the
    # meaning found came only from the sequestered report's SCT item.
    condition = release_condition(
        _coverage(
            SourceValue(MEANING, "LO", "Chest"),
            SourceValue(SCHEME, "SH", "SCT"),
            written=(SourceValue(SCHEME, "SH", "99LOCAL"),),
        ),
        _written(SERIES_DESCRIPTION),
    )

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [("(0008,103E)", Exemption.UNWRITTEN_CODE_MEANING)]


def test_only_a_meaning_whose_own_item_names_a_listed_scheme_is_coded():
    meaning = SourceValue(MEANING, "LO", "Chest")
    other = ElementPath((*CONTENT, ("(0040,A168)", 1)), CODE_MEANING)
    values = (
        meaning,
        SourceValue(SCHEME, "SH", "SCT"),
        SourceValue(other, "LO", "Chest"),  # an item without a designator
        SourceValue(ElementPath(other.items, DESIGNATOR), "SH", "99LOCAL\\SCT"),
    )

    assert standard_code_meanings(values) == {meaning}
    assert unwritten(_instance(values)).coded == {meaning}
    assert not standard_code_meanings((SourceValue(SCHEME, "SH", "SCT"),))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_person_name_from_unwritten_instances_still_withholds():
    name = ElementPath(CONTENT, "(0040,A123)")
    condition = release_condition(
        _coverage(SourceValue(name, "PN", "AXIAL^CHEST")),
        _written(_element(0x0008103E, "LO", "AXIAL CHEST")),
    )

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted


# The transform's evidence.


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _collected(result):
    return result.evidence.collected


def _unwritten(result):
    return result.evidence.unwritten


def test_a_sequestered_instance_gives_every_value_it_collected_as_unwritten():
    transform = InstanceTransform(
        compose_custom_policy((UIDS,)), KEY, unvalidated_policy=True
    )

    report = _transformed(transform, reports.x_ray_dose_report())
    image = _transformed(transform, synthetic.ct_slice(0))

    assert isinstance(report, run.Sequestered)
    assert isinstance(image, run.Transformed)
    assert _collected(report)
    assert _unwritten(report) == frozenset(_collected(report))
    assert _collected(image)
    assert not _unwritten(image)


# Runs of CT slices beside a dose report that the release does not support.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, transform, **descriptors):
    """Run three CT slices of the dose report's study, then the report."""
    slices = [synthetic.ct_slice(number) for number in range(3)]
    for dataset in slices:
        dataset.StudyInstanceUID = reports.STUDY
        for keyword, value in descriptors.items():
            setattr(dataset, keyword, value)
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate([*slices, reports.x_ray_dose_report()]):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    return [outcome.status for outcome in result.outcomes], report


def _counts(report, exemption):
    return {
        entry["found_in"]: entry["count"]
        for entry in report["exempted_findings"]
        if entry["exemption"] == exemption
    }


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_under_retain_uids_a_sequestered_reports_study_uid_withholds_nothing(
    tmp_path,
):
    """The report's removed scope of accumulation names the study.

    TID 10001's scope of accumulation gives the study's Study Instance UID
    as a UID (0040,A124), which Table E.1-1 gives U under every option, so
    it is collected and searched for, and found in each slice's kept Study
    Instance UID.
    """
    transform = InstanceTransform(
        compose_custom_policy((UIDS,)), KEY, unvalidated_policy=True
    )

    statuses, report = _run(tmp_path, transform)

    assert statuses == [*[run.Status.RELEASED] * 3, run.Status.SEQUESTERED]
    assert _counts(report, Exemption.UNWRITTEN_UID.value) == {STUDY_INSTANCE_UID: 3}
    released = sorted((tmp_path / "release").rglob("*.dcm"))
    assert {pydicom.dcmread(path).StudyInstanceUID for path in released} == {
        reports.STUDY
    }


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_sequestered_reports_target_region_holds_no_kept_description(tmp_path):
    """The report's target region is SCT 816094009 "Chest".

    Clean Descriptors keeps the slices' Series Description by its technique
    vocabulary, and the residual search finds the report's removed Code
    Meaning in it.
    """
    cleaning = DescriptorCleaning(
        None,
        ReviewedNames.empty(),
        reviewed_descriptors=ReviewedDescriptors.empty(),
    )
    transform = InstanceTransform(
        compose_policy("basic-clean-descriptors"),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
    )

    statuses, report = _run(tmp_path, transform, SeriesDescription="AXIAL CHEST")

    assert statuses == [*[run.Status.RELEASED] * 3, run.Status.SEQUESTERED]
    assert _counts(report, Exemption.UNWRITTEN_CODE_MEANING.value) == {"(0008,103E)": 3}
    released = sorted((tmp_path / "release").rglob("*.dcm"))
    assert {pydicom.dcmread(path).SeriesDescription for path in released} == {
        "AXIAL CHEST"
    }
