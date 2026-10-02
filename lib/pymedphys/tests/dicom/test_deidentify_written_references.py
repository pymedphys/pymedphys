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

"""The second pass: what a run wrote refers to itself as its inputs did."""

import logging
import re
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import uid_roles, uids, written_references
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.reference_graph import build_reference_graph
from pymedphys._dicom.deidentify.references import (
    IDENTITY_TAGS,
    REFERENCE_TAGS,
    InstanceRecord,
)

from . import _synthetic_references as synthetic

WrittenFinding = written_references.WrittenFinding
ORIGINAL = written_references.WrittenFindingKind.ORIGINAL_UID
IDENTIFIER = written_references.WrittenFindingKind.MISMATCHED_IDENTIFIER
REFERENCE = written_references.WrittenFindingKind.MISMATCHED_REFERENCE
UNWRITTEN = written_references.WrittenFindingKind.UNWRITTEN_TARGET
UNRESOLVED = written_references.WrittenFindingKind.UNRESOLVED_REFERENCE
SHARED = written_references.WrittenFindingKind.SHARED_REPLACEMENT
DUPLICATE = written_references.WrittenFindingKind.DUPLICATE_INSTANCE
SOP_INSTANCE_UID, SERIES_INSTANCE_UID, STUDY_INSTANCE_UID = (
    "(0008,0018)",
    "(0020,000E)",
    "(0020,000D)",
)
KEY = DeidKey(bytes(range(32)))
OTHER_KEY = DeidKey(bytes(range(1, 33)))
# Positions in synthetic.collection().
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")
# The attributes whose values the synthetic de-identifier replaces.
UID_TAGS = frozenset(
    pydicom.tag.Tag(int(tag[1:5], 16), int(tag[6:10], 16))
    for tag in (*IDENTITY_TAGS.values(), *REFERENCE_TAGS)
)


def _replaced(dataset, key=KEY, keep=()):
    """Return ``dataset`` with each identity and reference UID replaced.

    This stands in for a run that writes the replacement of every UID at an
    identity or reference site, except the source values in ``keep``.
    """
    copy = synthetic.read(synthetic.written(dataset))

    def replace(each, element):
        del each
        if element.tag in UID_TAGS and element.value and element.value not in keep:
            element.value = uids.transform_uid(
                key, uid_roles.UIDRole.INSTANCE, element.value
            )[0]

    copy.walk(replace)
    del copy.file_meta
    return copy


def _verify(inputs, written, key=KEY):
    """Verify ``written``, data sets by input position, against ``inputs``."""
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    return written_references.verify_written_references(
        key,
        graph,
        {position: synthetic.record(each) for position, each in written.items()},
    )


def _all_replaced(inputs, **kwargs):
    return {position: _replaced(each, **kwargs) for position, each in enumerate(inputs)}


def _finding(kind, position, attribute, count=1):
    return WrittenFinding(kind, ((position,),), attribute, count)


@pytest.mark.pydicom
def test_the_reference_and_identity_tags_are_instance_uids():
    roles = uid_roles.load_uid_roles()

    for tag in (*IDENTITY_TAGS.values(), *REFERENCE_TAGS):
        assert roles.role(tag) is uid_roles.UIDRole.INSTANCE


@pytest.mark.pydicom
def test_a_consistently_replaced_collection_has_no_findings():
    inputs = synthetic.collection()

    assert not _verify(inputs, _all_replaced(inputs))


@pytest.mark.pydicom
def test_nothing_written_has_no_findings():
    assert not _verify(synthetic.collection(), {})


@pytest.mark.pydicom
def test_the_findings_are_by_position_in_the_graph():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[PLAN].SOPInstanceUID = synthetic.PLAN

    assert _verify(inputs, written) == (
        _finding(ORIGINAL, PLAN, (SOP_INSTANCE_UID,)),
        _finding(UNRESOLVED, DOSE, synthetic.REFERENCED_PLAN),
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "keyword, tag",
    [
        ("SOPInstanceUID", SOP_INSTANCE_UID),
        ("SeriesInstanceUID", SERIES_INSTANCE_UID),
        ("StudyInstanceUID", STUDY_INSTANCE_UID),
    ],
)
def test_a_kept_identifier_is_an_original_uid(keyword, tag):
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    setattr(written[0], keyword, getattr(inputs[0], keyword))

    findings = _verify(inputs, written)

    assert findings[0] == _finding(ORIGINAL, 0, (tag,))
    assert {finding.kind for finding in findings} <= {ORIGINAL, UNRESOLVED}


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "tag", [SOP_INSTANCE_UID, SERIES_INSTANCE_UID, STUDY_INSTANCE_UID]
)
def test_an_identifier_replaced_under_another_key_is_mismatched(tag):
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[1] = _replaced(inputs[1], key=OTHER_KEY)

    findings = _verify(inputs, written)

    assert _finding(IDENTIFIER, 1, (tag,)) in findings
    assert {finding.kind for finding in findings} <= {
        IDENTIFIER,
        REFERENCE,
        UNRESOLVED,
    }


@pytest.mark.pydicom
def test_a_slice_written_in_another_series_than_its_input_series_is_mismatched():
    # Each slice of one input series must be written in one series.
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[2].SeriesInstanceUID = "2.25.9999"

    assert _verify(inputs, written) == (
        _finding(IDENTIFIER, 2, (SERIES_INSTANCE_UID,)),
    )


@pytest.mark.pydicom
@pytest.mark.parametrize("keyword", ["SOPInstanceUID", "StudyInstanceUID"])
def test_an_absent_identifier_is_mismatched(keyword):
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    delattr(written[0], keyword)

    findings = _verify(inputs, written)

    tag = pydicom.tag.Tag(pydicom.datadict.tag_for_keyword(keyword))
    assert findings[0] == _finding(
        IDENTIFIER, 0, (f"({tag.group:04X},{tag.element:04X})",)
    )


@pytest.mark.pydicom
def test_an_input_without_an_identifier_is_not_checked_for_it():
    inputs = synthetic.collection()
    del inputs[PLAN].SeriesInstanceUID
    written = _all_replaced(inputs)
    written[PLAN].SeriesInstanceUID = "2.25.9999"

    assert not _verify(inputs, written)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "position, attribute, value",
    [
        (PLAN, synthetic.REFERENCED_STRUCTURE_SET, synthetic.STRUCTURE_SET),
        (PLAN, synthetic.REFERENCED_DOSE, synthetic.DOSE),
        (DOSE, synthetic.REFERENCED_PLAN, synthetic.PLAN),
        (STRUCTURE_SET, synthetic.RT_REFERENCED_STUDY, synthetic.STUDY),
        (STRUCTURE_SET, synthetic.RT_REFERENCED_SERIES, synthetic.CT_SERIES),
        (STRUCTURE_SET, synthetic.CONTOUR_IMAGES, synthetic.CT_SLICES[1]),
    ],
)
def test_a_kept_reference_is_an_original_uid(position, attribute, value):
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[position] = _replaced(inputs[position], keep={value})
    # Only the reference: the instance's own identifiers are replaced.
    for keyword in ("SOPInstanceUID", "SeriesInstanceUID", "StudyInstanceUID"):
        setattr(
            written[position], keyword, getattr(_replaced(inputs[position]), keyword)
        )

    expected = [_finding(ORIGINAL, position, attribute)]
    if attribute == synthetic.CONTOUR_IMAGES:
        # The structure set references each slice at two sites.
        expected.append(_finding(ORIGINAL, position, synthetic.ROI_CONTOUR_IMAGES))
    assert _verify(inputs, written) == tuple(expected)


@pytest.mark.pydicom
def test_each_kept_value_at_a_site_is_counted_once():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[STRUCTURE_SET] = _replaced(
        inputs[STRUCTURE_SET], keep=set(synthetic.CT_SLICES[:2])
    )

    assert _verify(inputs, written) == (
        _finding(ORIGINAL, STRUCTURE_SET, synthetic.CONTOUR_IMAGES, 2),
        _finding(ORIGINAL, STRUCTURE_SET, synthetic.ROI_CONTOUR_IMAGES, 2),
    )


@pytest.mark.pydicom
def test_a_reference_to_another_written_instance_is_mismatched():
    # The plan's dose reference is the replacement of the structure set's
    # UID, which resolves, but is not what the input referred to there.
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[PLAN].ReferencedDoseSequence[0].ReferencedSOPInstanceUID = written[
        STRUCTURE_SET
    ].SOPInstanceUID

    assert _verify(inputs, written) == (
        _finding(REFERENCE, PLAN, synthetic.REFERENCED_DOSE),
    )


@pytest.mark.pydicom
def test_a_reference_replaced_under_another_key_is_mismatched():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[PLAN].ReferencedDoseSequence[
        0
    ].ReferencedSOPInstanceUID = uids.transform_uid(
        OTHER_KEY, uid_roles.UIDRole.INSTANCE, synthetic.DOSE
    )[0]

    assert _verify(inputs, written) == (
        _finding(REFERENCE, PLAN, synthetic.REFERENCED_DOSE),
    )


@pytest.mark.pydicom
def test_an_emptied_reference_is_mismatched():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[PLAN].ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID = ""

    assert _verify(inputs, written) == (
        _finding(REFERENCE, PLAN, synthetic.REFERENCED_STRUCTURE_SET),
    )


@pytest.mark.pydicom
def test_a_removed_reference_sequence_is_not_reported():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    del written[PLAN].ReferencedDoseSequence

    assert not _verify(inputs, written)


@pytest.mark.pydicom
def test_a_reference_added_at_a_site_without_one_is_mismatched():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[0].ReferencedImageSequence = [
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, written[1].SOPInstanceUID)
    ]

    assert _verify(inputs, written) == (
        _finding(REFERENCE, 0, synthetic.REFERENCED_IMAGE),
    )


@pytest.mark.pydicom
def test_a_source_uid_in_an_identifier_the_input_lacked_is_an_original_uid():
    inputs = synthetic.collection()
    del inputs[PLAN].SeriesInstanceUID
    written = _all_replaced(inputs)
    written[PLAN].SeriesInstanceUID = synthetic.CT_SERIES

    assert _finding(ORIGINAL, PLAN, (SERIES_INSTANCE_UID,)) in _verify(inputs, written)


@pytest.mark.pydicom
def test_a_reference_to_an_instance_that_was_not_written_is_reported():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    del written[DOSE]

    assert _verify(inputs, written) == (
        _finding(UNWRITTEN, PLAN, synthetic.REFERENCED_DOSE),
    )


@pytest.mark.pydicom
def test_references_to_slices_that_were_not_written_are_counted_once():
    # The reference to the slices' series still resolves, to the third.
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    del written[0], written[1]

    assert _verify(inputs, written) == (
        _finding(UNWRITTEN, STRUCTURE_SET, synthetic.CONTOUR_IMAGES, 2),
        _finding(UNWRITTEN, STRUCTURE_SET, synthetic.ROI_CONTOUR_IMAGES, 2),
    )


@pytest.mark.pydicom
def test_a_reference_to_a_series_none_of_which_was_written_is_reported():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    del written[0], written[1], written[2]

    assert _finding(UNWRITTEN, STRUCTURE_SET, synthetic.RT_REFERENCED_SERIES) in (
        _verify(inputs, written)
    )


@pytest.mark.pydicom
def test_a_reference_to_a_series_written_under_another_uid_is_unresolved():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    for position in (0, 1, 2):
        written[position].SeriesInstanceUID = "2.25.9999"

    assert _verify(inputs, written) == (
        *(
            _finding(IDENTIFIER, position, (SERIES_INSTANCE_UID,))
            for position in (0, 1, 2)
        ),
        _finding(UNRESOLVED, STRUCTURE_SET, synthetic.RT_REFERENCED_SERIES),
    )


@pytest.mark.pydicom
def test_a_series_reference_resolves_only_to_a_series():
    # The series' replacement is written, but as an instance's UID.
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    series = written[0].SeriesInstanceUID
    for position in (0, 1, 2):
        written[position].SeriesInstanceUID = "2.25.9999"
    written[0].SOPInstanceUID = series

    assert _finding(UNRESOLVED, STRUCTURE_SET, synthetic.RT_REFERENCED_SERIES) in (
        _verify(inputs, written)
    )


@pytest.mark.pydicom
def test_a_reference_to_a_written_instance_with_a_mismatched_uid_is_unresolved():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[DOSE].SOPInstanceUID = "2.25.9999"

    assert _verify(inputs, written) == (
        _finding(IDENTIFIER, DOSE, (SOP_INSTANCE_UID,)),
        _finding(UNRESOLVED, PLAN, synthetic.REFERENCED_DOSE),
    )


@pytest.mark.pydicom
def test_a_dangling_reference_need_not_resolve_but_must_be_replaced():
    inputs = synthetic.collection()
    inputs[0].ReferencedImageSequence = [
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, "2.25.9010")
    ]
    graph_findings = build_reference_graph(
        [synthetic.record(each) for each in inputs]
    ).findings
    assert graph_findings  # The graph reports it as dangling.
    written = _all_replaced(inputs)

    assert not _verify(inputs, written)

    written = _all_replaced(inputs, keep={"2.25.9010"})

    assert _verify(inputs, written) == (
        _finding(ORIGINAL, 0, synthetic.REFERENCED_IMAGE),
    )


@pytest.mark.pydicom
def test_a_well_known_reference_is_retained():
    inputs = synthetic.collection()
    inputs[0].ReferencedImageSequence = [
        synthetic.reference(None, synthetic.HOT_IRON_COLOR_PALETTE)
    ]
    written = _all_replaced(inputs)

    assert (
        written[0].ReferencedImageSequence[0].ReferencedSOPInstanceUID
        == synthetic.HOT_IRON_COLOR_PALETTE
    )
    assert not _verify(inputs, written)


@pytest.mark.pydicom
def test_a_duplicate_written_once_resolves_for_each_copy():
    inputs = synthetic.collection() + [synthetic.ct_slice(0)]
    written = _all_replaced(inputs)
    del written[6]

    assert not _verify(inputs, written)

    written = _all_replaced(inputs)
    del written[0]

    assert not _verify(inputs, written)


@pytest.mark.pydicom
def test_conflicting_copies_written_with_one_uid_are_reported():
    copy = synthetic.ct_slice(0)
    copy.SliceLocation = "999"
    inputs = synthetic.collection() + [copy]

    assert _verify(inputs, _all_replaced(inputs)) == (
        WrittenFinding(DUPLICATE, ((0, 6),), (SOP_INSTANCE_UID,), 1),
    )


@pytest.mark.pydicom
def test_a_shared_replacement_is_reported(monkeypatch):
    # Two input UIDs whose replacements collide, as SHA-1 names almost never
    # do, are written with the same value.
    collide = {synthetic.CT_SLICES[0], synthetic.CT_SLICES[1]}
    transform = uids.transform_uid

    def colliding(key, role, uid):
        if uid in collide:
            return transform(key, role, synthetic.CT_SLICES[0])
        return transform(key, role, uid)

    monkeypatch.setattr(uids, "transform_uid", colliding)
    monkeypatch.setattr(written_references, "transform_uid", colliding)
    inputs = synthetic.collection()

    # The two slices are then also written with one SOP Instance UID.
    assert _verify(inputs, _all_replaced(inputs)) == (
        WrittenFinding(SHARED, ((0, STRUCTURE_SET), (1, STRUCTURE_SET)), ()),
        WrittenFinding(DUPLICATE, ((0, 1),), (SOP_INSTANCE_UID,), 1),
    )


@pytest.mark.pydicom
def test_a_position_outside_the_graph_is_refused():
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    record = synthetic.record(_replaced(inputs[0]))

    for position in (-1, len(inputs), True, "0"):
        with pytest.raises(ValueError, match="not one of the graph's inputs"):
            written_references.verify_written_references(KEY, graph, {position: record})


def _text_values(dataset):
    for element in dataset.iterall():
        if element.VR in ("LO", "PN", "UI") and element.VM == 1:
            yield str(element.value)


@pytest.mark.pydicom
def test_findings_contain_no_values():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[PLAN] = _replaced(inputs[PLAN], keep={synthetic.PLAN})
    written[DOSE].SOPInstanceUID = "2.25.9999"
    del written[1]

    findings = _verify(inputs, written)

    assert {finding.kind for finding in findings} == {
        ORIGINAL,
        IDENTIFIER,
        UNWRITTEN,
        UNRESOLVED,
    }
    shown = repr(findings)
    values = {
        value for each in (*inputs, *written.values()) for value in _text_values(each)
    }
    assert {synthetic.PATIENT_ID, synthetic.PLAN, "2.25.9999"} <= values
    for value in values:
        assert value not in shown
    for finding in findings:
        assert all(TAG.fullmatch(tag) for tag in finding.attribute)
        assert all(
            isinstance(position, int)
            for group in finding.instances
            for position in group
        )


@pytest.mark.pydicom
def test_verifying_neither_warns_nor_logs(caplog, capsys):
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    written = _all_replaced(inputs)
    written[DOSE].SOPInstanceUID = "2.25.9999"
    records = {position: synthetic.record(each) for position, each in written.items()}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG):
            findings = written_references.verify_written_references(KEY, graph, records)

    assert findings
    assert not caught
    assert not caplog.records
    assert capsys.readouterr() == ("", "")


@pytest.mark.pydicom
def test_findings_are_ordered_by_kind_then_position_then_attribute():
    inputs = synthetic.collection()
    written = _all_replaced(inputs)
    written[DOSE].SOPInstanceUID = synthetic.DOSE
    written[STRUCTURE_SET] = _replaced(
        inputs[STRUCTURE_SET], keep={synthetic.CT_SLICES[2]}
    )
    del written[1]

    findings = _verify(inputs, written)

    assert findings == (
        _finding(ORIGINAL, STRUCTURE_SET, synthetic.CONTOUR_IMAGES),
        _finding(ORIGINAL, STRUCTURE_SET, synthetic.ROI_CONTOUR_IMAGES),
        _finding(ORIGINAL, DOSE, (SOP_INSTANCE_UID,)),
        _finding(UNWRITTEN, STRUCTURE_SET, synthetic.CONTOUR_IMAGES),
        _finding(UNWRITTEN, STRUCTURE_SET, synthetic.ROI_CONTOUR_IMAGES),
        _finding(UNRESOLVED, PLAN, synthetic.REFERENCED_DOSE),
    )


@pytest.mark.pydicom
def test_written_files_are_read_from_their_bytes():
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    records = {
        position: InstanceRecord.from_file(synthetic.written(_replaced(each)))
        for position, each in enumerate(inputs)
    }

    assert not written_references.verify_written_references(KEY, graph, records)
