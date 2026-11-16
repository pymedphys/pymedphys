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

"""Residual text found in a private creator that the selected safe private list keeps.

Under the Retain Safe Private Option, a kept private creator holds the block
name that the run's list matched, so a removed value found in it is that
vendor text (D-042). These tests use the creators that the shipped lists
keep, and invented values elsewhere.
"""

import io
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import policy, release_report, run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import (
    EQUIPMENT_SOURCES,
    Exemption,
    kept_creators,
    vendor_creators,
)
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.safe_private import (
    SafePrivateList,
    load_safe_private_rules,
)
from pymedphys._dicom.deidentify.tcia_private_tags import tcia_safe_private_rules

from . import _synthetic_references as synthetic

# A creator that only TCIA's dictionary keeps, in group 0009 and not 0011,
# and that PS3.15 Table E.3.10-1 does not list.
GE_PET = "GEMS_PETD_01"
# A creator that both lists keep in group 7053, and that the table lists.
PHILIPS_PET = "Philips PET Private Group"
HOSPITAL = "ZARQUON HOSPITAL"
OPTIONS = (policy.SAFE_PRIVATE,)
LISTS = {
    SafePrivateList.TCIA: (0x00090010, GE_PET),
    SafePrivateList.REVIEWED: (0x70530010, PHILIPS_PET),
}


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("latin-1") if isinstance(value, str) else value
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


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + meta + b"".join(elements)


def _coverage(*removed, options=OPTIONS, safe_private_list=None):
    values = tuple(
        SourceValue(source if isinstance(source, ElementPath) else _top(source), vr, v)
        for source, vr, v in removed
    )
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=values,
        options=options,
        safe_private_list=safe_private_list,
    )


def _top(tag):
    return ElementPath((), tag)


def _kept_creator(chosen):
    tag, creator = LISTS[chosen]
    return _element(tag, "LO", creator)


def _whys(condition):
    return [(finding.location.element.tag, why) for finding, why in condition.exempted]


# The creators that each list keeps.


def test_each_list_keeps_its_creators_by_group():
    tcia = kept_creators(SafePrivateList.TCIA)
    reviewed = kept_creators(SafePrivateList.REVIEWED)

    assert (0x0009, GE_PET) in tcia
    assert (0x0011, GE_PET) not in tcia
    assert all(creator != GE_PET for _, creator in reviewed)
    assert (0x7053, PHILIPS_PET) in tcia and (0x7053, PHILIPS_PET) in reviewed
    assert GE_PET not in vendor_creators() and PHILIPS_PET in vendor_creators()


def test_a_list_keeps_only_creators_of_rules_that_retain():
    for chosen in SafePrivateList:
        assert kept_creators(chosen) == frozenset(
            (rule.group, rule.private_creator) for rule in _rules(chosen).retained()
        )


def _rules(chosen):
    if chosen is SafePrivateList.TCIA:
        return tcia_safe_private_rules()
    return load_safe_private_rules()


# The coverage records the list.


def test_a_coverage_records_the_list_and_carries_it_through_a_merge():
    tcia = _coverage(safe_private_list=SafePrivateList.TCIA)
    reviewed = _coverage(safe_private_list=SafePrivateList.REVIEWED)
    none = _coverage(options=())

    assert Coverage.merge(tcia, tcia).safe_private_list is SafePrivateList.TCIA
    assert Coverage.merge(tcia, reviewed).safe_private_list is None
    assert Coverage.merge(tcia, none).safe_private_list is None
    assert Coverage.merge().safe_private_list is None
    assert none.safe_private_list is None


def test_a_coverage_refuses_a_list_that_is_not_one_or_without_the_option():
    with pytest.raises(TypeError, match="safe_private_list"):
        _coverage(safe_private_list="tcia")
    with pytest.raises(ValueError, match="Retain Safe Private"):
        _coverage(options=(), safe_private_list=SafePrivateList.TCIA)


# Findings that a kept creator explains.


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.10-01")
@pytest.mark.parametrize("chosen", list(SafePrivateList), ids=lambda c: c.value)
@pytest.mark.parametrize(
    "source",
    [
        _top("(0011,0010)"),  # the creator of another group
        ElementPath((("(0117,1024)", 0),), "(0117,0010)"),  # in an item
        _top("(0009,1002)"),  # a private data element
        *map(_top, sorted(EQUIPMENT_SOURCES)),
    ],
    ids=str,
)
def test_a_value_found_in_a_creator_that_the_list_keeps_is_released(chosen, source):
    creator = LISTS[chosen][1]
    written = _written(_kept_creator(chosen))
    coverage = _coverage((source, "LO", creator), safe_private_list=chosen)

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.RELEASE, condition.reasons
    found_in = f"({LISTS[chosen][0] >> 16:04X},{LISTS[chosen][0] & 0xFFFF:04X})"
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    vendor = group % 2 == 1 and element <= 0xFF and creator in vendor_creators()
    assert _whys(condition) == [
        (found_in, Exemption.VENDOR_CREATOR if vendor else Exemption.RETAINED_CREATOR)
    ]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_creator_kept_in_an_item_explains_as_one_at_the_top_level():
    written = _written(
        _sequence(0x00081111, [_element(0x00090010, "LO", GE_PET)]),
    )
    coverage = _coverage(
        ("(0011,0010)", "LO", GE_PET), safe_private_list=SafePrivateList.TCIA
    )

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.RELEASE, condition.reasons
    assert _whys(condition) == [("(0009,0010)", Exemption.RETAINED_CREATOR)]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_every_pooled_value_need_not_be_the_creator():
    # What is written in the kept creator is the list's name, whichever of
    # the source's values the search found there.
    written = _written(_element(0x00090010, "LO", GE_PET))
    coverage = _coverage(
        ("(0011,0010)", "LO", GE_PET),
        ("(0011,0010)", "LO", HOSPITAL),
        safe_private_list=SafePrivateList.TCIA,
    )

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.RELEASE, condition.reasons


# Findings that stay under review or withhold.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    ["(0008,0080)", "(0008,1010)", "(0008,1040)", "(0008,103E)", "(0008,0302)"],
    ids=["institution", "station", "department", "series", "creator-reference"],
)
def test_another_source_found_in_a_kept_creator_goes_to_review(source):
    written = _written(_kept_creator(SafePrivateList.TCIA))
    coverage = _coverage((source, "LO", GE_PET), safe_private_list=SafePrivateList.TCIA)

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "options, chosen",
    [((), None), (OPTIONS, None), (OPTIONS, SafePrivateList.REVIEWED)],
    ids=["no-option", "no-list", "reviewed-list"],
)
def test_a_creator_that_the_selected_list_does_not_keep_explains_nothing(
    options, chosen
):
    written = _written(_element(0x00090010, "LO", GE_PET))
    coverage = _coverage(
        ("(0011,0010)", "LO", GE_PET), options=options, safe_private_list=chosen
    )

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "tag, value",
    [
        (0x00110010, GE_PET),  # kept in another group than the list keeps it
        (0x00090010, GE_PET.lower()),  # in another case
        (0x00090010, " " + GE_PET),  # with a leading space
        (0x00090010, f"{GE_PET} {HOSPITAL}"),  # with more text
        (0x00090010, f"{GE_PET}\\{GE_PET}"),  # two values
        (0x00091001, GE_PET),  # a kept data element of the block
        (0x0008103E, GE_PET),  # Series Description, which is not a creator
    ],
    ids=[
        "other-group",
        "other-case",
        "leading-space",
        "more-text",
        "two-values",
        "data-element",
        "not-private",
    ],
)
def test_text_found_anywhere_else_goes_to_review(tag, value):
    written = _written(_element(tag, "LO", value))
    coverage = _coverage(
        ("(0013,1010)", "LO", GE_PET), safe_private_list=SafePrivateList.TCIA
    )

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.QC_REVIEW
    assert Exemption.RETAINED_CREATOR not in {why for _, why in condition.exempted}


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source, vr, code",
    [
        ("(0010,0010)", "PN", ReasonCode.RESIDUAL_PERSON_NAME),
        ("(0008,0018)", "UI", ReasonCode.RESIDUAL_UID),
        ("(0010,0020)", "LO", ReasonCode.RESIDUAL_DIRECT_IDENTIFIER),
    ],
    ids=["person-name", "uid", "direct-identifier"],
)
def test_a_person_name_uid_or_direct_identifier_in_a_kept_creator_withholds(
    source, vr, code
):
    written = _written(_element(0x00090010, "LO", GE_PET))
    coverage = _coverage((source, vr, GE_PET), safe_private_list=SafePrivateList.TCIA)

    condition = release_condition(coverage, written)

    assert condition.decision is Decision.WITHHOLD
    assert [reason.code for reason in condition.reasons] == [code]
    assert not condition.exempted


# A run under the Option.

KEY = DeidKey(bytes(range(32)))
SAFE_PRIVATE_POLICY = policy.compose_custom_policy([policy.SAFE_PRIVATE])


def _instance():
    """A CT slice whose GE PET block TCIA keeps in 0009 and not in 0011."""
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00090010, "LO", GE_PET)
    dataset.add_new(0x00091038, "FL", 1.5)
    dataset.add_new(0x00110010, "LO", GE_PET)
    dataset.add_new(0x00111010, "US", 7)
    return dataset


def _transformed(chosen, dataset):
    data = synthetic.written(dataset)
    transform = InstanceTransform(
        SAFE_PRIVATE_POLICY, KEY, safe_private_list=chosen, unvalidated_policy=True
    )
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return result


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.10-01")
@pytest.mark.parametrize("chosen", list(SafePrivateList), ids=lambda c: c.value)
def test_a_run_records_its_list_and_releases_the_kept_block(chosen):
    result = _transformed(chosen, _instance())

    assert isinstance(result.evidence, Coverage)
    assert result.evidence.safe_private_list is chosen  # pylint: disable=no-member
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert 0x00110010 not in written
    condition = release_condition(result.evidence, result.data)
    assert condition.decision is Decision.RELEASE, condition.reasons
    if chosen is SafePrivateList.TCIA:
        assert written[0x00090010].value == GE_PET
        assert _whys(condition) == [("(0009,0010)", Exemption.RETAINED_CREATOR)]
    else:
        assert 0x00090010 not in written
        assert not condition.exempted


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.10-01")
@pytest.mark.parametrize("chosen", list(SafePrivateList), ids=lambda c: c.value)
def test_a_device_manufacturer_found_in_the_kept_philips_pet_creator_is_released(
    chosen,
):
    # Both lists keep the Philips PET block, which Table E.3.10-1 lists; the
    # removed Secondary Capture Device Manufacturer is no creator, so only
    # the kept creator explains it.
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00181016, "LO", PHILIPS_PET)
    dataset.add_new(0x70530010, "LO", PHILIPS_PET)
    dataset.add_new(0x70531000, "DS", "1.5")

    result = _transformed(chosen, dataset)

    written = pydicom.dcmread(io.BytesIO(result.data))
    assert 0x00181016 not in written
    assert written[0x70530010].value == PHILIPS_PET
    condition = release_condition(result.evidence, result.data)
    assert condition.decision is Decision.RELEASE, condition.reasons
    assert [
        (finding.source.tag, finding.location.element.tag, why)
        for finding, why in condition.exempted
    ] == [("(0018,1016)", "(7053,0010)", Exemption.RETAINED_CREATOR)]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_run_without_the_option_records_no_list():
    data = synthetic.written(_instance())
    transform = InstanceTransform(
        policy.compose_policy("basic"), KEY, unvalidated_policy=True
    )

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, Coverage)
    assert result.evidence.safe_private_list is None  # pylint: disable=no-member


# The release report.


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_report_counts_findings_that_a_kept_creator_explains():
    written = _written(_element(0x00090010, "LO", GE_PET))
    coverage = _coverage(
        ("(0011,0010)", "LO", GE_PET), safe_private_list=SafePrivateList.TCIA
    )

    exempted = release_report.exempted_findings(
        [release_condition(coverage, written).exempted]
    )

    assert exempted == (
        release_report.ExemptedFindings(
            "retained-creator", "(0011,0010)", "(0009,0010)", 1
        ),
    )
    assert release_report.FORMAT == "pymedphys-deid-release-report/68"
