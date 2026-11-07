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

"""Residual text findings whose source is a removed copy of a kept code.

Equipment copies a requested procedure's code, in Requested Procedure Code
Sequence (0032,1064), into the procedure's own Procedure Code Sequence
(0008,1032). The Basic Profile removes the request with Request Attributes
Sequence (0040,0275) and keeps the procedure's code, so the residual search
collects the request's Code Value, Coding Scheme Designator, and Code
Meaning, and finds each in the same attribute of the kept code. Where every
instance of the subject that collected the request's value removed it, and
it equals a whole value of the same attribute of a kept code item, the copy
reveals nothing that the kept code does not, so the finding is explained
(D-032). Every other finding in the kept code, such as a removed Study
Description in its local meaning, is decided as before.
"""

import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_custom_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import Exemption
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
# Invented values of a local code, distinctive enough that nothing else in a
# file matches them.
VALUE = "ZQ0042"
DESIGNATOR = "99ZARQ"
MEANING = "ZARQUON HEAD SCAN"
CODE_VALUE = "(0008,0100)"
CODING_SCHEME_DESIGNATOR = "(0008,0102)"
CODE_MEANING = "(0008,0104)"
REQUEST_ATTRIBUTES = "(0040,0275)"
REQUESTED_PROCEDURE_CODE = "(0032,1064)"
STUDY_DESCRIPTION = ElementPath((), "(0008,1030)")


def _requested(tag, request=0, item=0):
    """The path of an attribute of a requested procedure's code item."""
    return ElementPath(
        ((REQUEST_ATTRIBUTES, request), (REQUESTED_PROCEDURE_CODE, item)), tag
    )


REQUESTED = {
    CODE_VALUE: (_requested(CODE_VALUE), "SH", VALUE),
    CODING_SCHEME_DESIGNATOR: (_requested(CODING_SCHEME_DESIGNATOR), "SH", DESIGNATOR),
    CODE_MEANING: (_requested(CODE_MEANING), "LO", MEANING),
}


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("ascii")
    value += b" " * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _sequence(tag, *items):
    """A sequence of undefined length, with items of undefined length."""
    group, element = divmod(tag, 0x10000)
    header = struct.pack("<HH2sHI", group, element, b"SQ", 0, 0xFFFFFFFF)
    body = b"".join(
        struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF)
        + b"".join(item)
        + struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
        for item in items
    )
    return header + body + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)


def _code(value=VALUE, designator=DESIGNATOR, meaning=MEANING):
    """The elements of a code item, in the order of their tags."""
    return [
        _element(0x00080100, "SH", value),
        _element(0x00080102, "SH", designator),
        _element(0x00080104, "LO", meaning),
    ]


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    syntax = _element(0x00020010, "UI", "1.2.840.10008.1.2.1")
    return bytes(128) + b"DICM" + syntax + b"".join(elements)


# The procedure's own code, as the Basic Profile keeps it.
KEPT_CODE = _written(_sequence(0x00081032, _code()))


def _instance(values, removed=None):
    """The coverage of one written instance that collected ``values``.

    Each of ``values`` is removed unless ``removed`` names those that are.
    """
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        removed=frozenset(values if removed is None else removed),
    )


def _value(source, vr, value):
    return SourceValue(source, vr, value)


def _exempted(condition):
    return [
        (f.source.tag, f.location.element.tag, why) for f, why in condition.exempted
    ]


def _reviews_for_text(condition):
    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted
    assert {reason.code for reason in condition.reasons} == {ReasonCode.RESIDUAL_TEXT}


# The exemption.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("tag", sorted(REQUESTED))
def test_a_removed_request_code_equal_to_the_kept_code_is_released(tag):
    coverage = Coverage.merge(_instance((_value(*REQUESTED[tag]),)))

    condition = release_condition(coverage, KEPT_CODE)

    assert condition.decision is Decision.RELEASE
    assert not condition.reasons
    assert _exempted(condition) == [(tag, tag, Exemption.COPIED_REQUEST_CODE)]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_whole_copied_code_is_released_and_each_finding_kept_in_the_search():
    values = tuple(_value(*REQUESTED[tag]) for tag in sorted(REQUESTED))

    condition = release_condition(Coverage.merge(_instance(values)), KEPT_CODE)

    assert condition.decision is Decision.RELEASE
    assert sorted(_exempted(condition)) == [
        (tag, tag, Exemption.COPIED_REQUEST_CODE) for tag in sorted(REQUESTED)
    ]
    assert len(condition.search.findings) == 3


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_request_code_directly_in_the_sequence_at_the_top_level_is_explained():
    source = ElementPath(((REQUESTED_PROCEDURE_CODE, 0),), CODE_MEANING)
    coverage = Coverage.merge(_instance((_value(source, "LO", MEANING),)))

    condition = release_condition(coverage, KEPT_CODE)

    assert _exempted(condition) == [
        (CODE_MEANING, CODE_MEANING, Exemption.COPIED_REQUEST_CODE)
    ]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_other_text_found_in_the_kept_code_still_goes_to_review():
    """D-032's concern: a local meaning that copies a free-text description."""
    values = (
        _value(*REQUESTED[CODE_MEANING]),
        _value(STUDY_DESCRIPTION, "LO", MEANING),
    )

    condition = release_condition(Coverage.merge(_instance(values)), KEPT_CODE)

    assert condition.decision is Decision.QC_REVIEW
    assert _exempted(condition) == [
        (CODE_MEANING, CODE_MEANING, Exemption.COPIED_REQUEST_CODE)
    ]
    assert [(reason.code, reason.path) for reason in condition.reasons] == [
        (ReasonCode.RESIDUAL_TEXT, STUDY_DESCRIPTION)
    ]


# What stays under review.


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_request_code_that_a_written_instance_holds_still_goes_to_review():
    value = _value(*REQUESTED[CODE_MEANING])
    removing = _instance((value,))
    keeping = _instance((value,), removed=())

    _reviews_for_text(release_condition(Coverage.merge(keeping), KEPT_CODE))
    _reviews_for_text(release_condition(Coverage.merge(removing, keeping), KEPT_CODE))


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        # Scheduled Protocol Code Sequence, in the same request.
        ElementPath(((REQUEST_ATTRIBUTES, 0), ("(0040,0008)", 0)), CODE_MEANING),
        # An equivalent code of the requested procedure's code.
        ElementPath(
            (
                (REQUEST_ATTRIBUTES, 0),
                (REQUESTED_PROCEDURE_CODE, 0),
                ("(0008,0121)", 0),
            ),
            CODE_MEANING,
        ),
        # A Code Meaning outside any item.
        ElementPath((), CODE_MEANING),
        # Requested Procedure Description, a free-text copy.
        ElementPath((), "(0032,1060)"),
    ],
    ids=["scheduled-protocol", "equivalent-code", "no-item", "description"],
)
def test_the_same_text_from_another_source_still_goes_to_review(source):
    coverage = Coverage.merge(_instance((_value(source, "LO", MEANING),)))

    _reviews_for_text(release_condition(coverage, KEPT_CODE))


SHORT = "ZARQUON SCAN"  # a meaning that a Code Value can hold


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "written, value",
    [
        # A longer kept meaning that holds the request's.
        (
            _written(_sequence(0x00081032, _code(meaning=f"{MEANING} WITH DYE"))),
            MEANING,
        ),
        # The same text in another case.
        (_written(_sequence(0x00081032, _code(meaning=MEANING.title()))), MEANING),
        # The request's meaning in the kept code's value.
        (
            _written(_sequence(0x00081032, _code(value=SHORT, meaning="ROUTINE"))),
            SHORT,
        ),
        # The request's meaning in kept text outside a code item.
        (_written(_element(0x0008103E, "LO", MEANING)), MEANING),
    ],
    ids=["contained", "case", "other-attribute", "outside-a-code"],
)
def test_a_request_code_not_equal_to_the_same_attribute_of_a_kept_code_stays(
    written, value
):
    source = _requested(CODE_MEANING)
    coverage = Coverage.merge(_instance((_value(source, "LO", value),)))

    _reviews_for_text(release_condition(coverage, written))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_pooled_request_value_found_inside_the_kept_code_stays_under_review():
    """Another instance's request at the same place can hold other text."""
    whole = _value(*REQUESTED[CODE_MEANING])
    part = _value(_requested(CODE_MEANING), "LO", "HEAD SCAN")

    condition = release_condition(
        Coverage.merge(_instance((whole,)), _instance((part,))), KEPT_CODE
    )

    _reviews_for_text(condition)


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_copied_request_code_leaves_a_person_name_in_the_kept_code_withheld():
    name = ElementPath((), "(0010,0010)")
    written = _written(_sequence(0x00081032, _code(meaning="ZARQUON^HEAD")))
    values = (
        _value(_requested(CODE_MEANING), "LO", "ZARQUON^HEAD"),
        _value(name, "PN", "ZARQUON^HEAD"),
    )

    condition = release_condition(Coverage.merge(_instance(values)), written)

    assert condition.decision is Decision.WITHHOLD
    assert _exempted(condition) == [
        (CODE_MEANING, CODE_MEANING, Exemption.COPIED_REQUEST_CODE)
    ]
    assert [reason.code for reason in condition.reasons] == [
        ReasonCode.RESIDUAL_PERSON_NAME
    ]


# The transform's evidence and a run.


def _with_copied_code(dataset):
    """Give ``dataset`` a request whose code equipment copied to the procedure."""
    code = pydicom.Dataset()
    code.CodeValue, code.CodingSchemeDesignator, code.CodeMeaning = (
        VALUE,
        DESIGNATOR,
        MEANING,
    )
    request = pydicom.Dataset()
    request.RequestedProcedureCodeSequence = [code]
    dataset.RequestAttributesSequence = [request]
    procedure = pydicom.Dataset()
    procedure.update(code)
    dataset.ProcedureCodeSequence = [procedure]
    return dataset


def _collected(result):
    return result.evidence.collected


def _removed(result):
    return result.evidence.removed


def test_the_basic_profile_removes_the_request_and_keeps_the_procedure_code():
    transform = InstanceTransform(
        compose_custom_policy(()), KEY, unvalidated_policy=True
    )
    data = synthetic.written(_with_copied_code(synthetic.ct_slice(0)))

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed)
    collected = {value.source: value for value in _collected(result)}
    for tag in REQUESTED:
        assert collected[_requested(tag)] in _removed(result)
    procedure = ElementPath((("(0008,1032)", 0),), CODE_MEANING)
    assert procedure not in collected


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_under_basic_ct_slices_with_a_copied_request_code_are_released(tmp_path):
    transform = InstanceTransform(
        compose_custom_policy(()), KEY, unvalidated_policy=True
    )
    source = tmp_path / "source"
    source.mkdir()
    for number in range(3):
        dataset = _with_copied_code(synthetic.ct_slice(number))
        (source / f"{number}.dcm").write_bytes(synthetic.written(dataset))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 3
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    assert sorted(
        (entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.COPIED_REQUEST_CODE.value
    ) == [
        (
            f"{REQUEST_ATTRIBUTES} > {REQUESTED_PROCEDURE_CODE} > {tag}",
            f"(0008,1032) > {tag}",
            3,
        )
        for tag in sorted(REQUESTED)
    ]
    for path in sorted((tmp_path / "release").rglob("*.dcm")):
        dataset = pydicom.dcmread(path)
        assert "RequestAttributesSequence" not in dataset
        assert dataset.ProcedureCodeSequence[0].CodeMeaning == MEANING
