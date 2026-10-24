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

"""Private text under Retain Safe Private, cleaned under Clean Descriptors.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import io
import json
import re

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    element_rules,
    output_names,
    policy,
    qc_pack,
    run,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    FORMAT,
    Held,
    Outcome,
    ReviewedDescriptor,
    ReviewedDescriptors,
    ReviewedDescriptorsError,
    clean_descriptor_values,
    descriptor_vr,
    private_descriptor,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames
from pymedphys._dicom.deidentify.run_qc import DescriptorMaterial, RetainedText
from pymedphys._dicom.deidentify.run_report import descriptor_counts
from pymedphys._dicom.deidentify.safe_private import SafePrivateList
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.technique_descriptors import (
    load_technique_vocabulary,
)
from pymedphys._dicom.deidentify.uids import replacement_uid
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
SAFE_PRIVATE = policy.SAFE_PRIVATE
CLEAN_DESCRIPTORS = policy.CLEAN_DESCRIPTORS
BOTH = (SAFE_PRIVATE, CLEAN_DESCRIPTORS)
CLEAN_DESCRIPTORS_CODE = "113105"
SAFE_PRIVATE_CODE = "113111"
GE = "GEMS_ACQU_01"
PET = "Philips PET Private Group"
SEQUENCE_NAME = '(0019,"GEMS_ACQU_01",9E) LO'
CREATOR = ElementPath((), "(0019,0010)")
TEXT = ElementPath((), "(0019,109E)")
SPEED = ElementPath((), "(0019,1023)")
TRANSFER_SYNTAXES = (
    synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    synthetic.IMPLICIT_VR_LITTLE_ENDIAN,
)


def _slice(*elements, block=0x10):
    """A CT slice with GE's creator at ``block`` and the given elements."""
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00190000 | block, "LO", GE)
    for tag, vr, value in elements:
        dataset.add_new(tag, vr, value)
    return dataset


def _named(value, block=0x10):
    """A slice whose GE block holds the pulse sequence name ``value``."""
    return _slice((0x0019009E | block << 8, "LO", value), block=block)


def _reviewed(*decisions):
    reviewed = ReviewedDescriptors.empty()
    for attribute, value, review, *to in decisions:
        reviewed.record(attribute, value, ReviewedDescriptor(review, *to))
    return reviewed


def _transform(reviewed=None, options=BOTH, safe_private_list=None):
    cleaning = None
    if CLEAN_DESCRIPTORS in options:
        cleaning = DescriptorCleaning(
            None,
            ReviewedNames.empty(),
            reviewed_descriptors=reviewed or ReviewedDescriptors.empty(),
        )
    extra = (
        {} if safe_private_list is None else {"safe_private_list": safe_private_list}
    )
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
        **extra,
    )


def _result(transform, dataset, transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN):
    data = synthetic.written(dataset, transfer_syntax)
    return transform(data, InstanceRecord.from_file(data))


def _written(result):
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


def _private(dataset):
    return {
        f"({e.tag.group:04X},{e.tag.element:04X})": e.value
        for e in dataset
        if e.tag.group % 2
    }


def _collected(result):
    """Return the places of the values that the residual search looks for."""
    return [value.source for value in result.evidence.collected]


def _codes(written):
    return [item.CodeValue for item in written.DeidentificationMethodCodeSequence]


def _material(result):
    return [item for item in result.qc if isinstance(item, DescriptorMaterial)]


def _plan(
    dataset,
    options=BOTH,
    transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    safe_private_list=SafePrivateList.REVIEWED,
):
    source = read_source(synthetic.written(dataset, transfer_syntax))
    rules = element_rules.ElementRules(
        policy.compose_custom_policy(options), safe_private_list=safe_private_list
    )
    return plan_instance(source, rules, load_iod_tables().iods["CT Image"])


def test_a_private_attribute_is_decided_on_by_its_creator_element_and_vr():
    assert private_descriptor(0x0019, GE, 0x9E, "LO") == SEQUENCE_NAME
    assert descriptor_vr(SEQUENCE_NAME) == "LO"
    assert private_descriptor(0x2001, 'A "B", C', 0x05, "ST") == (
        '(2001,"A "B", C",05) ST'
    )
    for group, creator, element, vr in (
        (0x0018, GE, 0x9E, "LO"),  # not a private group
        (0x0001, GE, 0x9E, "LO"),  # not open to private use
        (0x0019, "", 0x9E, "LO"),
        (0x0019, GE + " ", 0x9E, "LO"),  # padded
        (0x0019, "GE\\MS", 0x9E, "LO"),
        (0x0019, "GEMS_ÄCQU", 0x9E, "LO"),
        (0x0019, GE, 0x100, "LO"),
        (0x0019, GE, 0x9E, "DS"),
        (0x0019, GE, 0x9E, "PN"),
    ):
        with pytest.raises(ValueError):
            private_descriptor(group, creator, element, vr)
    for written in (
        '(0019,"GEMS_ACQU_01",9e) LO',
        '(0019,"GEMS_ACQU_01",9E)',
        "(0019,GEMS_ACQU_01,9E) LO",
        '(0019,"GEMS_ACQU_01",9E)  LO',
    ):
        assert descriptor_vr(written) is None


def test_a_list_records_and_saves_decisions_on_private_text(tmp_path):
    path = tmp_path / "reviewed-descriptors.json"
    reviewed = ReviewedDescriptors.open(path)
    reviewed.record(SEQUENCE_NAME, "FSE-XL", ReviewedDescriptor(Review.KEEP))
    reviewed.record(
        '(0043,"GEMS_PARM_01",27) SH', "A", ReviewedDescriptor(Review.MAP, "B")
    )
    reviewed.save()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["format"] == FORMAT == "pymedphys-deid-reviewed-descriptors/2"
    reopened = ReviewedDescriptors.open(path)
    assert reopened.get(SEQUENCE_NAME, "FSE-XL") == ReviewedDescriptor(Review.KEEP)
    assert reopened.keyed_digest(KEY) == reviewed.keyed_digest(KEY)
    # A value of SH or LO holds no backslash, and a mapping fits its VR.
    with pytest.raises(ReviewedDescriptorsError, match="backslash"):
        reviewed.record(SEQUENCE_NAME, "A\\B", ReviewedDescriptor(Review.KEEP))
    with pytest.raises(ReviewedDescriptorsError, match="longer"):
        reviewed.record(
            '(0043,"GEMS_PARM_01",27) SH',
            "C",
            ReviewedDescriptor(Review.MAP, "X" * 17),
        )
    with pytest.raises(ReviewedDescriptorsError, match="not a descriptor"):
        reviewed.record(
            '(0019,"GEMS_ACQU_01",23) DS', "1", ReviewedDescriptor(Review.KEEP)
        )


def test_a_list_of_the_earlier_format_is_read_without_private_text(tmp_path):
    earlier = tmp_path / "earlier.json"
    attributes = {"(0008,103E)": {"AXIAL": {"review": "keep"}}}
    earlier.write_text(
        json.dumps(
            {
                "format": "pymedphys-deid-reviewed-descriptors/1",
                "attributes": attributes,
            }
        ),
        encoding="utf-8",
    )

    assert ReviewedDescriptors.open(earlier).get("(0008,103E)", "AXIAL")

    attributes[SEQUENCE_NAME] = {"FSE": {"review": "keep"}}
    earlier.write_text(
        json.dumps(
            {
                "format": "pymedphys-deid-reviewed-descriptors/1",
                "attributes": attributes,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReviewedDescriptorsError, match="earlier format"):
        ReviewedDescriptors.open(earlier)


def test_the_technique_vocabulary_keeps_no_private_text():
    vocabulary = load_technique_vocabulary()
    assert vocabulary.keeps("(0018,0024)", "FSE")  # Sequence Name

    (result,) = clean_descriptor_values(
        SEQUENCE_NAME,
        ["FSE"],
        ReviewedDescriptors.empty(),
        identifiers=[],
        vocabulary=vocabulary,
    )

    assert (result.outcome, result.held_because) == (Outcome.HELD, Held.UNREVIEWED)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_the_plan_cleans_private_text_only_under_clean_descriptors_with_its_vr(
    transfer_syntax,
):
    dataset = _named("FSE")
    explicit = transfer_syntax == synthetic.EXPLICIT_VR_LITTLE_ENDIAN

    both = _plan(dataset, BOTH, transfer_syntax)
    alone = _plan(dataset, (SAFE_PRIVATE,), transfer_syntax)

    actions = {element.path: element.action for element in both.elements}
    assert actions[TEXT] == ("C" if explicit else "X")
    assert actions[CREATOR] == ("K" if explicit else "X")
    assert dict(both.private_texts) == ({TEXT: SEQUENCE_NAME} if explicit else {})
    assert {e.path: e.action for e in alone.elements}[TEXT] == "X"
    assert not alone.private_texts


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_private_text_written_as_un_is_removed():
    data = synthetic.written(_named("SENTINEL"))
    # The same bytes, with VR UN and a four-byte length.
    data = data.replace(
        b"\x19\x00\x9e\x10LO\x08\x00SENTINEL",
        b"\x19\x00\x9e\x10UN\x00\x00\x08\x00\x00\x00SENTINEL",
    )

    result = _transform(_reviewed((SEQUENCE_NAME, "SENTINEL", Review.KEEP)))(
        data, InstanceRecord.from_file(data)
    )

    written = _written(result)
    assert b"SENTINEL" not in result.data
    assert not _private(written)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_private_text_that_a_reviewer_keeps_is_kept_with_its_creator():
    result = _result(
        _transform(_reviewed((SEQUENCE_NAME, "FSE-XL", Review.KEEP))), _named("FSE-XL")
    )

    written = _written(result)
    assert _private(written) == {"(0019,0010)": GE, "(0019,109E)": "FSE-XL"}
    assert set(_codes(written)) == {"113100", CLEAN_DESCRIPTORS_CODE, SAFE_PRIVATE_CODE}
    (material,) = _material(result)
    assert material.attribute == SEQUENCE_NAME and material.applied
    assert [r.outcome for r in material.results] == [Outcome.KEPT]
    assert RetainedText("FSE-XL", TEXT) in result.qc
    # Its source is left out of the residual search, as a kept descriptor's
    # is, so the kept value is not found in what is written; so is its
    # creator's.
    assert TEXT not in _collected(result)
    assert CREATOR not in _collected(result)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_private_text_with_more_values_than_its_vm_is_removed():
    reviewed = _reviewed(
        (SEQUENCE_NAME, "SENTINEL", Review.KEEP), (SEQUENCE_NAME, "FSE", Review.KEEP)
    )

    plan = _plan(_named("SENTINEL\\FSE"))
    result = _result(_transform(reviewed), _named("SENTINEL\\FSE"))

    assert not plan.private_texts
    assert b"SENTINEL" not in result.data
    assert not _private(_written(result))


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_reviewer_s_mapping_is_written():
    reviewed = _reviewed((SEQUENCE_NAME, "SENTINEL FSE", Review.MAP, "FSE"))

    result = _result(_transform(reviewed), _named("SENTINEL FSE"))

    assert b"SENTINEL" not in result.data
    assert _private(_written(result))["(0019,109E)"] == "FSE"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_decision_applies_wherever_the_creator_reserves_its_block():
    reviewed = _reviewed((SEQUENCE_NAME, "FSE", Review.KEEP))

    result = _result(_transform(reviewed), _named("FSE", block=0x42))

    assert _private(_written(result)) == {"(0019,0042)": GE, "(0019,429E)": "FSE"}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_private_text_that_no_reviewer_decided_on_is_removed_and_listed():
    result = _result(_transform(), _named("SENTINEL"))

    written = _written(result)
    assert b"SENTINEL" not in result.data
    assert not _private(written)
    # Removing it still meets Clean Descriptors.
    assert set(_codes(written)) == {"113100", CLEAN_DESCRIPTORS_CODE, SAFE_PRIVATE_CODE}
    (material,) = _material(result)
    assert material.attribute == SEQUENCE_NAME
    assert material.sources == ("SENTINEL",) and not material.applied
    # The creator removed with it is searched for, as a removed one is.
    assert {TEXT, CREATOR} <= set(_collected(result))
    assert [(r.outcome, r.held_because) for r in material.results] == [
        (Outcome.HELD, Held.UNREVIEWED)
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_creator_removed_with_its_text_is_not_listed_as_retained():
    result = _result(_transform(), _named("SENTINEL"))

    assert not [item for item in result.qc if isinstance(item, RetainedText)]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_creator_is_kept_for_what_else_its_block_keeps():
    dataset = _slice((0x00191023, "DS", "39.375"), (0x0019109E, "LO", "SENTINEL"))

    result = _result(_transform(), dataset)

    assert _private(_written(result)) == {"(0019,0010)": GE, "(0019,1023)": "39.375"}
    assert CREATOR not in _collected(result)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_kept_text_that_echoes_the_patient_is_removed():
    family = synthetic.PATIENTS_NAME.split("^", maxsplit=1)[0]
    reviewed = _reviewed((SEQUENCE_NAME, f"FSE {family}", Review.KEEP))

    result = _result(_transform(reviewed), _named(f"FSE {family}"))

    assert family.encode() not in result.data.split(b"\x10\x00\x10\x00")[0]
    assert not _private(_written(result))
    (material,) = _material(result)
    assert material.results[0].held_because is Held.ECHOES_IDENTIFIER


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_private_text_that_cannot_be_read_as_its_character_set_is_removed():
    # Text outside ISO 646 with no Specific Character Set is read as
    # ISO 8859-1 for the search, but is not cleaned, and removed rather
    # than sequestering its instance.
    data = synthetic.written(_named("SENTINELX"))
    data = data.replace(b"SENTINELX ", b"SENTINEL\xe9 ")
    reviewed = _reviewed((SEQUENCE_NAME, "SENTINELé", Review.KEEP))

    result = _transform(reviewed)(data, InstanceRecord.from_file(data))

    assert b"SENTINEL" not in result.data
    assert not _private(_written(result))
    assert not _material(result)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_undecodable_private_text_is_removed_rather_than_sequestering():
    dataset = _named("SENTINELX")
    dataset.SpecificCharacterSet = "ISO_IR 192"
    data = synthetic.written(dataset)
    data = data.replace(b"SENTINELX ", b"SENTINEL\xff ")

    result = _transform()(data, InstanceRecord.from_file(data))

    assert b"SENTINEL" not in result.data
    assert not _private(_written(result))


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "PS3.15-E.3.10-03")
def test_a_parsed_sequence_holding_only_text_is_kept_only_for_kept_text():
    item = pydicom.Dataset()
    item.add_new(0x70530010, "LO", PET)
    item.add_new(0x20010010, "LO", "Philips Imaging DD 001")
    item.add_new(0x2001105A, "ST", "SENTINEL NOTE")
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x70530010, "LO", PET)
    dataset.add_new(0x705310F0, "SQ", pydicom.Sequence([item]))
    within = ElementPath((("(7053,10F0)", 0),), "(2001,105A)")
    key = '(2001,"Philips Imaging DD 001",5A) ST'

    assert _plan(dataset).private_texts == {within: key}

    removed = _written(_result(_transform(), dataset))
    kept = _written(
        _result(_transform(_reviewed((key, "SENTINEL NOTE", Review.KEEP))), dataset)
    )

    assert not _private(removed)
    assert _private(kept)["(7053,0010)"] == PET
    (written_item,) = kept[0x705310F0].value
    assert _private(written_item) == {
        "(2001,0010)": "Philips Imaging DD 001",
        "(2001,105A)": "SENTINEL NOTE",
    }


def test_a_parsed_sequence_goes_whole_with_kept_text_where_other_text_is_held():
    item = pydicom.Dataset()
    item.add_new(0x20010010, "LO", "Philips Imaging DD 001")
    item.add_new(0x20011050, "LO", "ARROW")
    item.add_new(0x2001105A, "ST", "SENTINEL NOTE")
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x70530010, "LO", PET)
    dataset.add_new(0x705310F0, "SQ", pydicom.Sequence([item]))
    marker = '(2001,"Philips Imaging DD 001",50) LO'

    result = _result(_transform(_reviewed((marker, "ARROW", Review.KEEP))), dataset)

    # The note is held, so it takes its action without Clean Descriptors,
    # which removes the sequence that holds it, and the kept marker with it.
    assert not _private(_written(result))
    assert b"SENTINEL" not in result.data
    assert {m.attribute: m.applied for m in _material(result)} == {
        marker: False,
        '(2001,"Philips Imaging DD 001",5A) ST': False,
    }
    assert not [item for item in result.qc if isinstance(item, RetainedText)]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_text_that_an_instance_declares_safe_is_cleaned():
    dataset = _slice((0x00191099, "SH", "SENTINEL"))  # no rule
    item = pydicom.Dataset()
    item.PrivateGroupReference = 0x0019
    item.PrivateCreatorReference = GE
    item.BlockIdentifyingInformationStatus = "SAFE"
    dataset.PrivateDataElementCharacteristicsSequence = pydicom.Sequence([item])
    key = '(0019,"GEMS_ACQU_01",99) SH'

    removed = _written(_result(_transform(), dataset))
    kept = _written(
        _result(_transform(_reviewed((key, "SENTINEL", Review.KEEP))), dataset)
    )

    assert not _private(removed)
    assert _private(kept)["(0019,1099)"] == "SENTINEL"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "multiplicity, value, written",
    [
        ([2], "AX\\T1", True),
        # GBK writes U+4E57 as 81H 5CH, so its bytes count two values.
        ([2], "\u4e57", False),
        ([2, 0, 2], "AX\\T1\\\u4e57", False),
    ],
)
def test_declared_text_is_cleaned_only_where_its_decoded_values_meet_the_vm(
    multiplicity, value, written
):
    dataset = _slice((0x00191099, "LO", value))
    dataset.SpecificCharacterSet = "GBK"
    definition = pydicom.Dataset()
    definition.add_new(0x00080308, "US", 0x99)
    definition.add_new(0x00080309, "UL", multiplicity)
    definition.add_new(0x0008030A, "CS", "LO")
    item = pydicom.Dataset()
    item.PrivateGroupReference = 0x0019
    item.PrivateCreatorReference = GE
    item.BlockIdentifyingInformationStatus = "SAFE"
    item.add_new(0x00080310, "SQ", pydicom.Sequence([definition]))
    dataset.PrivateDataElementCharacteristicsSequence = pydicom.Sequence([item])
    key = '(0019,"GEMS_ACQU_01",99) LO'
    reviewed = _reviewed(*((key, each, Review.KEEP) for each in ("AX", "T1", "\u4e57")))

    plan = _plan(dataset)
    result = _result(_transform(reviewed), dataset)

    # The plan counts the raw bytes; cleaning counts the decoded values.
    assert plan.private_texts == {ElementPath((), "(0019,1099)"): key}
    assert ("(0019,1099)" in _private(_written(result))) is written


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_text_that_tcia_s_dictionary_keeps_is_cleaned():
    reviewed = _reviewed((SEQUENCE_NAME, "FSE", Review.KEEP))
    transform = _transform(reviewed, safe_private_list=SafePrivateList.TCIA)

    plan = _plan(_named("FSE"), safe_private_list=SafePrivateList.TCIA)
    written = _written(_result(transform, _named("FSE")))

    assert plan.private_texts == {TEXT: SEQUENCE_NAME}
    assert _private(written)["(0019,109E)"] == "FSE"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_withheld_instance_leaves_out_only_private_text_that_would_be_kept():
    # Responsible Person and Organization are required where present, and
    # the profile removes them, so the instance is withheld before cleaning.
    reviewed = _reviewed((SEQUENCE_NAME, "FSE", Review.KEEP))
    kept, unreviewed = _named("FSE"), _named("SENTINEL")
    held = _slice((0x00191023, "DS", "39.375"), (0x0019109E, "LO", "SENTINEL"))
    datasets = (kept, unreviewed, held)
    for dataset in datasets:
        dataset.ResponsiblePerson = "ROLE^PERSON"
        dataset.ResponsibleOrganization = "SENTINEL ORGANISATION"

    results = [_result(_transform(reviewed), each) for each in datasets]

    assert all(isinstance(result, run.Sequestered) for result in results)
    assert [TEXT in _collected(result) for result in results] == [False, True, True]
    # The creator is left out only where its block would still be written.
    assert [CREATOR in _collected(r) for r in results] == [False, True, False]


def test_the_qc_pack_and_report_name_private_text_by_its_key():
    result = _result(_transform(), _named("SENTINEL"))
    (material,) = _material(result)

    entry = qc_pack.DescriptorEntry(
        0,
        material.path,
        material.sources,
        material.results,
        material.applied,
        material.attribute,
    )
    public = qc_pack.DescriptorEntry(
        0, ElementPath((), "(0008,103E)"), ("A",), material.results, False
    )
    released = qc_pack.InstanceEntry(
        0,
        "in/a.dcm",
        qc_pack.Disposition.RELEASED,
        output=output_names.instance_path(
            patient_id="DEID-" + "A" * 16,
            study_instance_uid=replacement_uid(KEY, "2.25.1"),
            series_instance_uid=replacement_uid(KEY, "2.25.2"),
            sop_instance_uid=replacement_uid(KEY, "2.25.3"),
        ),
    )
    pack = qc_pack.QcPack(
        qc_pack.new_reference(), (released,), descriptors=(entry, public)
    )
    document = qc_pack.pack_document(pack)

    assert document["format"] == "pymedphys-deid-qc-pack/16"
    assert [d["attribute"] for d in document["descriptors"]] == [
        SEQUENCE_NAME,
        "(0008,103E)",
    ]
    assert [d["element"] for d in document["descriptors"]] == [
        "(0019,109E)",
        "(0008,103E)",
    ]
    with pytest.raises(qc_pack.QcPackError, match="private attribute's key"):
        qc_pack.DescriptorEntry(
            0, material.path, material.sources, material.results, False, "(0019,109E)"
        )
    # One attribute in two blocks is one attribute for the report's counts.
    other = DescriptorMaterial(
        ElementPath((), "(0019,429E)"),
        material.sources,
        material.results,
        False,
        SEQUENCE_NAME,
    )
    counts = descriptor_counts({0: [material], 1: [other]})
    assert counts.held == {Held.UNREVIEWED: 1}


def test_the_statement_lists_text_rules_and_says_how_text_is_cleaned():
    both = conformance.conformance_statement(
        policy.compose_custom_policy(BOTH), vocabulary=None
    )
    alone = conformance.conformance_statement(
        policy.compose_custom_policy((SAFE_PRIVATE,)), vocabulary=None
    )

    text = conformance_markdown.render_markdown(both)
    without = conformance_markdown.render_markdown(alone)

    row = f"| {GE} | (0019,xx9E) | LO | 1 | text | Internal Pulse Sequence Name |"
    assert row in text.splitlines() and row not in without
    assert len(both.safe_private) == len(alone.safe_private) + 44
    assert SEQUENCE_NAME in text and SEQUENCE_NAME not in without
    assert "private text is cleaned only under the Clean Descriptors" in without
    assert re.search(r"\bD-\d{3}\b", text) is None
