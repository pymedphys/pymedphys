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

"""Residual text findings whose source is a removed code's local designator.

A Coding Scheme Designator (0008,0102) names the scheme of its code item and
nothing else. Where de-identification removes a code item, such as a content
item that Clean Structured Content cannot keep, and the run keeps another
code item of the same local scheme, the residual search collects the removed
item's designator and finds it in the kept item's identical designator. The
finding reveals only that the two items shared a scheme, which the kept item
already shows, so it is explained (D-032). Text from any other source found
in a designator, a designator found inside a longer one or in any other
attribute, and every Code Meaning are decided as before.
"""

import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import policy, run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import Exemption
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.run_report import (
    RELEASE_REPORT,
    RELEASE_REPORT_MARKDOWN,
)

from . import _synthetic_references as synthetic
from . import _synthetic_structured_reports as reports

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
# An invented local scheme, distinctive enough that nothing else in a file
# matches it.
DESIGNATOR = "99ZARQ"
CODE_VALUE = "(0008,0100)"
CODING_SCHEME_DESIGNATOR = "(0008,0102)"
CODE_MEANING = "(0008,0104)"
CONTENT = "(0040,A730)"
CONCEPT_NAME = "(0040,A043)"
CONCEPT_CODE = "(0040,A168)"
INSTITUTION_CODE = "(0008,0082)"
INSTITUTION_NAME = ElementPath((), "(0008,0080)")
VERIFYING_ORGANIZATION = ElementPath((("(0040,A073)", 0),), "(0040,A027)")


def _removed_designator(*items):
    """The path of the designator of a removed content item's coded value."""
    return ElementPath(
        tuple((CONTENT, index) for index in items) + ((CONCEPT_CODE, 0),),
        CODING_SCHEME_DESIGNATOR,
    )


SOURCE = _removed_designator(0, 3)


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


def _code(value="ZQ7", designator=DESIGNATOR, meaning="ZARQUON SCORE"):
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


def _kept_item(**code):
    """A written file whose one content item has a concept name of the scheme."""
    content_item = [_sequence(0x0040A043, _code(**code))]
    return _written(_sequence(0x0040A730, content_item))


KEPT = _kept_item()


def _instance(values, removed=None):
    """The coverage of one written instance that collected ``values``.

    Each of ``values`` is removed unless ``removed`` names those that are.
    """
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        removed=frozenset(values if removed is None else removed),
    )


def _value(source, value=DESIGNATOR, vr="SH"):
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
def test_a_removed_designator_equal_to_a_kept_designator_is_released():
    condition = release_condition(Coverage.merge(_instance((_value(SOURCE),))), KEPT)

    assert condition.decision is Decision.RELEASE
    assert not condition.reasons
    assert _exempted(condition) == [
        (
            CODING_SCHEME_DESIGNATOR,
            CODING_SCHEME_DESIGNATOR,
            Exemption.SHARED_DESIGNATOR,
        )
    ]
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        # A removed content item's concept name.
        ElementPath(((CONTENT, 2), (CONCEPT_NAME, 0)), CODING_SCHEME_DESIGNATOR),
        # A removed code at the top level, such as a protocol's.
        ElementPath((("(0040,0260)", 0),), CODING_SCHEME_DESIGNATOR),
        # An equivalent code inside a removed code item.
        ElementPath(
            ((CONTENT, 1), (CONCEPT_CODE, 0), ("(0008,0121)", 0)),
            CODING_SCHEME_DESIGNATOR,
        ),
    ],
    ids=["concept-name", "top-level-code", "equivalent-code"],
)
def test_any_removed_standard_code_items_designator_is_explained(source):
    condition = release_condition(Coverage.merge(_instance((_value(source),))), KEPT)

    assert condition.decision is Decision.RELEASE
    assert [why for _, why in condition.exempted] == [Exemption.SHARED_DESIGNATOR]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_designator_is_released_in_a_kept_coded_value_too():
    written = _written(
        _sequence(0x0040A730, [_sequence(0x0040A168, _code(meaning="GRADE ONE"))])
    )

    condition = release_condition(Coverage.merge(_instance((_value(SOURCE),))), written)

    assert condition.decision is Decision.RELEASE
    assert [why for _, why in condition.exempted] == [Exemption.SHARED_DESIGNATOR]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_other_text_found_beside_the_shared_designator_still_goes_to_review():
    """The kept code's own text faces every other finding as before."""
    values = (
        _value(SOURCE),
        _value(ElementPath((), "(0008,1030)"), "ZARQUON SCORE", "LO"),
    )

    condition = release_condition(Coverage.merge(_instance(values)), KEPT)

    assert condition.decision is Decision.QC_REVIEW
    assert _exempted(condition) == [
        (
            CODING_SCHEME_DESIGNATOR,
            CODING_SCHEME_DESIGNATOR,
            Exemption.SHARED_DESIGNATOR,
        )
    ]
    assert [(reason.code, reason.path) for reason in condition.reasons] == [
        (ReasonCode.RESIDUAL_TEXT, ElementPath((), "(0008,1030)"))
    ]


# What stays under review.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source, vr",
    [
        # An organisation's name, which D-032 keeps under review in a
        # designator as in an equipment name: an in-house scheme can carry it.
        (VERIFYING_ORGANIZATION, "LO"),
        (INSTITUTION_NAME, "LO"),
        # A removed private creator, which the benchmark found in local
        # designators, unless Table E.3.10-1 lists it.
        (ElementPath((), "(0009,0010)"), "LO"),
        # A code's value or meaning that equals a designator.
        (ElementPath(((CONTENT, 0), (CONCEPT_CODE, 0)), CODE_VALUE), "SH"),
        (ElementPath(((CONTENT, 0), (CONCEPT_CODE, 0)), CODE_MEANING), "LO"),
        # A designator outside any item, which no code item holds.
        (ElementPath((), CODING_SCHEME_DESIGNATOR), "SH"),
        # The designator of a code that names an institution.
        (
            ElementPath(((INSTITUTION_CODE, 0),), CODING_SCHEME_DESIGNATOR),
            "SH",
        ),
        (
            ElementPath(
                (("(0040,A07C)", 0), (INSTITUTION_CODE, 0)), CODING_SCHEME_DESIGNATOR
            ),
            "SH",
        ),
        # A designator in a private sequence, whose items the vendor defines.
        (
            ElementPath((("(0009,1010)", 0),), CODING_SCHEME_DESIGNATOR),
            "SH",
        ),
    ],
    ids=[
        "verifying-organization",
        "institution-name",
        "private-creator",
        "code-value",
        "code-meaning",
        "no-item",
        "institution-code",
        "custodial-organization",
        "private-sequence",
    ],
)
def test_the_same_text_from_another_source_still_goes_to_review(source, vr):
    coverage = Coverage.merge(_instance((_value(source, vr=vr),)))

    _reviews_for_text(release_condition(coverage, KEPT))


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "written",
    [
        # A longer kept designator that holds the removed one.
        _kept_item(designator=f"{DESIGNATOR}X"),
        # The same text in another case.
        _kept_item(designator=DESIGNATOR.lower()),
        # The removed designator in a kept code's value or meaning.
        _kept_item(value=DESIGNATOR, designator="99YBEX"),
        _kept_item(meaning=f"{DESIGNATOR} SCORE", designator="99YBEX"),
        # The removed designator in kept text outside a code item.
        _written(_element(0x0008103E, "LO", DESIGNATOR)),
    ],
    ids=["contained", "case", "code-value", "code-meaning", "outside-a-code"],
)
def test_a_designator_not_equal_to_a_whole_kept_designator_stays(written):
    coverage = Coverage.merge(_instance((_value(SOURCE),)))

    _reviews_for_text(release_condition(coverage, written))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_designator_that_a_written_instance_holds_still_goes_to_review():
    value = _value(SOURCE)
    removing = _instance((value,))
    keeping = _instance((value,), removed=())

    _reviews_for_text(release_condition(Coverage.merge(keeping), KEPT))
    _reviews_for_text(release_condition(Coverage.merge(removing, keeping), KEPT))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_pooled_designator_found_inside_the_kept_one_stays_under_review():
    """Another instance's removed item at the same place can hold other text."""
    whole = _value(SOURCE)
    part = _value(SOURCE, "ZARQ")

    condition = release_condition(
        Coverage.merge(_instance((whole,)), _instance((part,))), KEPT
    )

    _reviews_for_text(condition)


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_local_meaning_equal_to_a_kept_meaning_still_goes_to_review():
    """A local scheme's meaning is the site's own text (D-032)."""
    source = ElementPath(((CONTENT, 0), (CONCEPT_CODE, 0)), CODE_MEANING)
    coverage = Coverage.merge(_instance((_value(source, "ZARQUON SCORE", "LO"),)))

    _reviews_for_text(release_condition(coverage, KEPT))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_shared_designator_leaves_a_person_name_in_it_withheld():
    name = ElementPath((), "(0010,0010)")
    values = (_value(SOURCE), _value(name, DESIGNATOR, "PN"))

    condition = release_condition(Coverage.merge(_instance(values)), KEPT)

    assert condition.decision is Decision.WITHHOLD
    assert [reason.code for reason in condition.reasons] == [
        ReasonCode.RESIDUAL_PERSON_NAME
    ]


# The transform's evidence and a run, under Clean Structured Content.

# A characteristic coded in NCIt, whose rows the pin leaves out, so that
# Clean Structured Content cannot keep its content item, and the coded
# values of a local scheme that the converter of an annotation tool writes.
CALCIFICATION = reports.Code("C3672", "NCIt", "Calcification")
ABSENT = reports.Code("ZQ1", DESIGNATOR, "ZARQUON ABSENT")
SCORE = reports.Code("ZQ7", DESIGNATOR, "ZARQUON SCORE")
MODERATE = reports.Code("ZQ3", DESIGNATOR, "ZARQUON MODERATE")
# An organisation that both made and verified a report.
ORGANISATION = "YBEXIAN LABS"


def _group(dataset):
    """The measurement group of a measurement report's Imaging Measurements."""
    return dataset.ContentSequence[-1].ContentSequence[0]


def _with_local_scheme(dataset):
    """Give a measurement report's group a removed and a kept local code.

    They follow its required items as qualitative evaluations (TID 1411
    row 21, CONTAINS CODE).
    """
    group = _group(dataset)
    group.ContentSequence.append(
        reports.item("CONTAINS", "CODE", CALCIFICATION, code=ABSENT)
    )
    group.ContentSequence.append(reports.item("CONTAINS", "CODE", SCORE, code=MODERATE))
    return dataset


def _report(**kwargs):
    return _with_local_scheme(reports.measurement_report(**kwargs))


def _transform():
    return InstanceTransform(
        policy.compose_custom_policy((policy.CLEAN_STRUCTURED_CONTENT,)),
        KEY,
        unvalidated_policy=True,
    )


def _collected(result):
    return result.evidence.collected


def _removed(result):
    return result.evidence.removed


def test_the_option_removes_the_ncit_item_and_keeps_the_local_one():
    data = synthetic.written(_report())

    result = _transform()(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    designators = [
        value
        for value in _collected(result)
        if value.source.tag == CODING_SCHEME_DESIGNATOR and value.value == DESIGNATOR
    ]
    assert designators
    assert all(value in _removed(result) for value in designators)
    written = pydicom.dcmread(pydicom.filebase.DicomBytesIO(result.data))
    group = _group(written)
    names = [each.ConceptNameCodeSequence[0] for each in group.ContentSequence]
    assert (SCORE.value, DESIGNATOR) in [
        (name.CodeValue, name.CodingSchemeDesignator) for name in names
    ]
    assert CALCIFICATION.value not in [name.CodeValue for name in names]


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, dataset):
    transform = _transform()
    source = tmp_path / "source"
    source.mkdir()
    (source / "report.dcm").write_bytes(synthetic.written(dataset))
    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    return result


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_report_whose_kept_and_removed_items_share_a_scheme_is_released(tmp_path):
    result = _run(tmp_path, _report())

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED]
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    shared = sorted(
        (entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.SHARED_DESIGNATOR.value
    )
    assert shared == sorted(
        {
            (
                f"{CONTENT} > {CONTENT} > {CONTENT} > {CONCEPT_CODE} > "
                f"{CODING_SCHEME_DESIGNATOR}",
                f"{CONTENT} > {CONTENT} > {CONTENT} > {tag} > "
                f"{CODING_SCHEME_DESIGNATOR}",
                1,
            )
            for tag in (CONCEPT_NAME, CONCEPT_CODE)
        }
    )
    markdown = (result.release / RELEASE_REPORT_MARKDOWN).read_text(encoding="utf-8")
    assert "a removed code's local coding scheme designator" in markdown
    assert Exemption.SHARED_DESIGNATOR.value in markdown
    assert DESIGNATOR not in markdown


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_verifying_organization_named_in_the_kept_manufacturer_is_reviewed(
    tmp_path,
):
    """D-032 keeps an organisation's name in an equipment name under review."""
    dataset = _report(verified=True)
    dataset.VerifyingObserverSequence[0].VerifyingOrganization = ORGANISATION
    dataset.Manufacturer = ORGANISATION

    result = _run(tmp_path, dataset)

    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW
    ]
    reasons = [str(reason) for reason in result.outcomes[0].reasons]
    assert reasons
    assert all("(0040,A073)[0] > (0040,A027): residual-text" in r for r in reasons)
