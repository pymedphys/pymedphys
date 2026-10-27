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

"""The Clean Structured Content Option, by the concept names of content items.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``. Content items whose concept names Table E.3.4-1 does
not list are coded in the invented local scheme ``99PMP``.
"""

import functools
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dev.deid_tables import generate
from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    content_items,
    policy,
    run,
    scope,
    standard,
    structured_content,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.element_rules import ElementRules, RuleSource
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
ENHANCED_CT = "08-ct-enhanced.dcm"
ACQUISITION_CONTEXT = "(0040,0555)"
SPECIMEN_PREPARATION = "(0040,0610)"
CONTENT = "(0040,A730)"
WAVEFORM_ANNOTATION = "(0040,B020)"
REFERENCED_CONTENT_ITEM = "(0040,DB73)"
REPORT = "Comprehensive SR"
TEXT_VALUE = "(0040,A160)"
PERSON_NAME = "(0040,A123)"
DATE = "(0040,A121)"
UID = "(0040,A124)"
SENTINEL = "SENTINEL"


def _transform(options, cleaning=None):
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
    )


def _cleaning():
    return DescriptorCleaning(None, ReviewedNames.empty())


@functools.cache
def _enhanced_ct_data():
    (file,) = (f for f in corpus_module.build_corpus().files if f.name == ENHANCED_CT)
    return file.data


def _enhanced_ct(*items):
    dataset = pydicom.dcmread(io.BytesIO(_enhanced_ct_data()))
    dataset.AcquisitionContextSequence = pydicom.Sequence(list(items))
    return dataset


def _code(value, designator, meaning):
    code = pydicom.Dataset()
    code.CodeValue = value
    code.CodingSchemeDesignator = designator
    code.CodeMeaning = meaning
    return code


def _item(value_type, concept, **values):
    """Return a content item with a concept name ``(value, designator, meaning)``."""
    item = pydicom.Dataset()
    item.ValueType = value_type
    item.ConceptNameCodeSequence = pydicom.Sequence([_code(*concept)])
    for keyword, value in values.items():
        setattr(item, keyword, value)
    return item


def _coded(meaning="Fixture context"):
    return _item(
        "CODE",
        ("CTX1", "99PMP", meaning),
        ConceptCodeSequence=pydicom.Sequence([_code("VAL1", "99PMP", "Fixture")]),
    )


def _numeric():
    item = _item("NUMERIC", ("NUM1", "99PMP", "Fixture number"), NumericValue="1.5")
    item.MeasurementUnitsCodeSequence = pydicom.Sequence(
        [_code("mm", "UCUM", "millimeter")]
    )
    return item


def _text(concept=("TXT1", "99PMP", "Fixture text"), value=f"{SENTINEL} TEXT"):
    return _item("TEXT", concept, TextValue=value)


PERSON_OBSERVER_NAME = ("121008", "DCM", "Person Observer Name")
ACCESSION_NUMBER = ("121022", "DCM", "Accession Number")
ACQUISITION_DATE = ("126201", "DCM", "Acquisition Date")
ACQUISITION_PROTOCOL = ("125203", "DCM", "Acquisition Protocol")
DEVICE_SERIAL_NUMBER = ("113880", "DCM", "Device Serial Number")
DEVICE_OBSERVER_UID = ("121012", "DCM", "Device Observer UID")
FINDING_SITE = ("363698007", "SCT", "Finding Site")
EQUIPMENT_IDENTIFICATION = ("121122", "DCM", "Equipment Identification")


def _written(options, dataset, cleaning=None):
    data = synthetic.written(dataset)
    result = _transform(options, cleaning)(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    return pydicom.dcmread(io.BytesIO(result.data))


def _actions(options, dataset, iod="Enhanced CT Image"):
    source = read_source(synthetic.written(dataset))
    return content_items.content_item_actions(
        source,
        policy.compose_custom_policy(options),
        load_iod_tables().iods[iod],
    )


def _rows():
    return {c.key: c for c in structured_content.load_table_e3_4_1().concepts}


def _row(concept, value_type):
    value, designator, _ = concept
    return _rows()[(designator, value, value_type)]


def _codes(dataset):
    # The corpus's source item, which the engine keeps, has no Code Value.
    return [
        item.get("CodeValue") for item in dataset.DeidentificationMethodCodeSequence
    ]


def _path(*items, tag):
    return ElementPath(tuple(items), tag)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_the_engine_applies_clean_structured_content():
    assert policy.ENGINE_APPLIES[CSC]
    assert CSC in policy.ENGINE_OPTIONS
    ElementRules(policy.compose_custom_policy([CSC]))


def test_table_e1_1_gives_c_to_the_four_sequences_of_content_items():
    rows = {
        row.tag
        for row in standard.load_table_e1_1().attributes
        if row.options.get(CSC) == "C"
    }

    assert rows == {
        ACQUISITION_CONTEXT,
        CONTENT,
        SPECIMEN_PREPARATION,
        WAVEFORM_ANNOTATION,
    }
    assert set(content_items.CONTENT_ITEM_SEQUENCES) == rows - {WAVEFORM_ANNOTATION}


@pytest.mark.parametrize(
    "concept, value_type, options, action",
    [
        (PERSON_OBSERVER_NAME, "PNAME", (), "D"),
        (ACCESSION_NUMBER, "TEXT", (), "X"),
        # X/D removes the item, which no template that the engine checks
        # requires.
        (DEVICE_SERIAL_NUMBER, "TEXT", (), "X"),
        (DEVICE_SERIAL_NUMBER, "TEXT", ("retain_device_identity",), "K"),
        (ACQUISITION_DATE, "DATE", ("retain_longitudinal_full_dates",), "K"),
        (ACQUISITION_DATE, "DATE", ("retain_longitudinal_modified_dates",), "C"),
        # Clean Descriptors' C falls back to the action without it (D-009).
        (ACQUISITION_PROTOCOL, "TEXT", ("clean_descriptors",), "X"),
        (FINDING_SITE, "TEXT", ("clean_descriptors",), "D"),
        (
            EQUIPMENT_IDENTIFICATION,
            "TEXT",
            ("retain_device_identity", "clean_descriptors"),
            "K",
        ),
        (DEVICE_OBSERVER_UID, "UIDREF", ("retain_uids",), "K"),
        (DEVICE_OBSERVER_UID, "UIDREF", (), "X"),
    ],
)
def test_each_concept_takes_the_action_its_options_give(
    concept, value_type, options, action
):
    row = _row(concept, value_type)

    assert content_items.concept_action(row, (CSC, *options)) == action
    assert content_items.concept_actions((CSC, *options))[row.key] == action


def test_c_applies_where_the_options_give_k_and_c():
    row = structured_content.ContentItemConcept(
        "Fixture",
        "1",
        "99PMP",
        "",
        "DATE",
        False,
        True,
        "X",
        {"retain_device_identity": "K", "retain_longitudinal_modified_dates": "C"},
    )

    assert content_items.concept_action(row, tuple(row.options)) == "C"
    assert content_items.concept_action(row, ("retain_device_identity",)) == "K"
    unknown = structured_content.ContentItemConcept(
        "Fixture", "1", "99PMP", "", "DATE", False, True, "D", {"retain_uids": "Z"}
    )
    assert content_items.concept_action(unknown, ("retain_uids",)) == "X"


def test_the_schemes_left_out_of_the_table_are_never_matched():
    left_out = set(generate.PIN.left_out_structured_content_schemes)

    assert left_out == content_items.UNMATCHED_SCHEMES


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("designator", ["SRT", "SNM3", "99SDM"])
def test_a_retired_snomed_code_is_looked_up_as_its_snomed_ct_code(designator):
    # PS3.16 Table O-1 maps G-C0E3 to Finding Site, SCT 363698007, whose
    # TEXT row of Table E.3.4-1 gives D.
    retired = _enhanced_ct(_text(("G-C0E3", designator, "Finding site")))
    expected = {
        _path(tag=ACQUISITION_CONTEXT): "K",
        _path((ACQUISITION_CONTEXT, 0), tag=TEXT_VALUE): "D",
    }

    assert dict(_actions((CSC,), retired)) == expected
    assert dict(_actions((CSC,), _enhanced_ct(_text(FINDING_SITE)))) == expected
    written = _written((CSC,), retired)
    assert len(written.AcquisitionContextSequence) == 1
    assert written.AcquisitionContextSequence[0].TextValue


def test_a_retired_snomed_code_of_an_unlisted_concept_is_not_listed():
    # Table O-1 maps T-D1100 to Head structure, SCT 69536005, which Table
    # E.3.4-1 does not list.
    head = _item(
        "CODE",
        ("T-D1100", "SRT", "Head"),
        ConceptCodeSequence=pydicom.Sequence([_code("VAL1", "99PMP", "Fixture")]),
    )
    dataset = _enhanced_ct(head)

    assert dict(_actions((CSC,), dataset)) == {_path(tag=ACQUISITION_CONTEXT): "K"}
    (written,) = _written((CSC,), dataset).AcquisitionContextSequence
    assert written.ConceptNameCodeSequence[0].CodeValue == "T-D1100"
    assert written.ConceptCodeSequence[0].CodeValue == "VAL1"


def test_a_retired_snomed_code_of_a_concept_to_remove_empties_its_sequence():
    # F-02455 is Social History, SCT 160476009, whose TEXT row gives X.
    dataset = _enhanced_ct(_coded(), _text(("F-02455", "SRT", "Social history")))

    assert not _actions((CSC,), dataset)


def test_nothing_is_given_without_the_option():
    dataset = _enhanced_ct(_coded())

    assert not _actions((), dataset)
    written = _written((), dataset)
    assert len(written.AcquisitionContextSequence) == 0


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_items_whose_concepts_the_table_does_not_list_keep_codes_and_numbers():
    dataset = _enhanced_ct(_coded(), _numeric(), _text())

    assert dict(_actions((CSC,), dataset)) == {_path(tag=ACQUISITION_CONTEXT): "K"}
    written = _written((CSC,), dataset)
    coded, numeric, text = written.AcquisitionContextSequence
    assert coded.ConceptCodeSequence[0].CodeValue == "VAL1"
    assert coded.ConceptNameCodeSequence[0].CodeMeaning == "Fixture context"
    assert numeric.ValueType == "NUMERIC"
    assert numeric.NumericValue == 1.5
    assert numeric.MeasurementUnitsCodeSequence[0].CodeValue == "mm"
    # Text Value's supplementary rule, X/Z/D, gives D where it is Type 1C.
    assert text.TextValue
    assert CSC_CODE in _codes(written)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_listed_concept_gives_its_value_its_action():
    dataset = _enhanced_ct(
        _coded(), _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    )
    item = (ACQUISITION_CONTEXT, 1)

    assert dict(_actions((CSC,), dataset)) == {
        _path(tag=ACQUISITION_CONTEXT): "K",
        _path(item, tag=PERSON_NAME): "D",
    }
    written = _written((CSC,), dataset)
    assert len(written.AcquisitionContextSequence) == 2
    assert written.AcquisitionContextSequence[1].PersonName


def test_the_walker_gives_the_content_item_actions_in_place_of_the_rules():
    dataset = _enhanced_ct(
        _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    )
    source = read_source(synthetic.written(dataset))
    iod = load_iod_tables().iods["Enhanced CT Image"]
    rules = ElementRules(policy.compose_custom_policy([CSC]))
    actions = content_items.content_item_actions(source, rules.policy, iod)

    planned = {e.path: e for e in plan_instance(source, rules, iod, actions).elements}
    without = {e.path: e for e in plan_instance(source, rules, iod).elements}

    sequence = _path(tag=ACQUISITION_CONTEXT)
    name = _path((ACQUISITION_CONTEXT, 0), tag=PERSON_NAME)
    assert planned[sequence].action == "K"
    assert planned[sequence].rule.source is RuleSource.CONTENT_ITEM
    assert planned[name].action == "D"
    assert planned[name].rule.source is RuleSource.CONTENT_ITEM
    assert without[sequence].action == "Z"
    assert without[name].removed_with == sequence


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "item",
    [
        _text(ACCESSION_NUMBER),
        _text(DEVICE_SERIAL_NUMBER),
        _item("DATE", ACQUISITION_DATE, Date="20260101"),
        # A concept name coded by a scheme whose rows the table cannot hold.
        _item("DATE", ("11778-8", "LN", "EDD"), Date="20260101"),
        # Retired SNOMED codes that PS3.16 Table O-1 does not map, one in
        # another case than the table's.
        _item("CODE", ("R-F0101", "SRT", "Fixture"), ConceptCodeSequence=[]),
        _item("CODE", ("F-0101", "SNM3", "Fixture"), ConceptCodeSequence=[]),
        _item("CODE", ("Z-99999", "99SDM", "Fixture"), ConceptCodeSequence=[]),
        _item("CODE", ("t-d1100", "SRT", "Fixture"), ConceptCodeSequence=[]),
    ],
)
def test_an_item_that_cannot_be_kept_gives_its_sequence_its_basic_action(item):
    dataset = _enhanced_ct(_coded(), item)

    assert not _actions((CSC,), dataset)
    written = _written((CSC,), dataset)
    # Type 2 here, so X/Z empties it.
    assert len(written.AcquisitionContextSequence) == 0
    assert CSC_CODE in _codes(written)


def _two_concept_names():
    item = _coded()
    item.ConceptNameCodeSequence.append(_code("CTX2", "99PMP", "Other"))
    return item


def _without(keyword):
    item = _coded()
    delattr(item, keyword)
    return item


def _without_code_value():
    item = _coded()
    del item.ConceptNameCodeSequence[0].CodeValue
    return item


def _without_designator():
    item = _coded()
    del item.ConceptNameCodeSequence[0].CodingSchemeDesignator
    return item


@pytest.mark.parametrize(
    "item",
    [
        _two_concept_names(),
        _without("ValueType"),
        _without("ConceptNameCodeSequence"),
        _without_code_value(),
        _without_designator(),
        _item("NOTATYPE", ("CTX1", "99PMP", "Fixture")),
    ],
)
def test_an_item_whose_concept_cannot_be_read_is_not_kept(item):
    assert not _actions((CSC,), _enhanced_ct(_coded(), item))


def _long_code_value(designator):
    item = _coded()
    code = item.ConceptNameCodeSequence[0]
    del code.CodeValue
    code.LongCodeValue = "FIXTURE-LONG-CODE-VALUE-0001"
    code.CodingSchemeDesignator = designator
    return item


def test_a_long_code_value_is_not_listed():
    assert dict(_actions((CSC,), _enhanced_ct(_long_code_value("99PMP")))) == {
        _path(tag=ACQUISITION_CONTEXT): "K"
    }


@pytest.mark.parametrize("designator", ["LN", "SRT"])
def test_a_long_code_value_of_an_unmatched_or_retired_scheme_is_not_kept(designator):
    # No SNOMED ID is a Long Code Value, so Table O-1 cannot map it.
    assert not _actions((CSC,), _enhanced_ct(_long_code_value(designator)))


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_modifiers_are_content_items_too():
    kept = _coded()
    kept.ContentItemModifierSequence = pydicom.Sequence(
        [_item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")]
    )
    removed = _coded()
    removed.ContentItemModifierSequence = pydicom.Sequence([_text(ACCESSION_NUMBER)])
    item = (ACQUISITION_CONTEXT, 0)

    assert dict(_actions((CSC,), _enhanced_ct(kept))) == {
        _path(tag=ACQUISITION_CONTEXT): "K",
        _path(item, ("(0040,0441)", 0), tag=PERSON_NAME): "D",
    }
    assert not _actions((CSC,), _enhanced_ct(removed))
    _written((CSC,), _enhanced_ct(kept))


def test_retain_device_identity_keeps_a_device_serial_number():
    value = "FIXTURE SERIAL 0001"
    dataset = _enhanced_ct(_text(DEVICE_SERIAL_NUMBER, value))
    options = (CSC, "retain_device_identity")

    assert (
        _actions(options, dataset)[_path((ACQUISITION_CONTEXT, 0), tag=TEXT_VALUE)]
        == "K"
    )
    written = _written(options, dataset)
    assert written.AcquisitionContextSequence[0].TextValue == value


def test_full_dates_keep_an_acquisition_date():
    dataset = _enhanced_ct(_item("DATE", ACQUISITION_DATE, Date="20260101"))

    written = _written((CSC, "retain_longitudinal_full_dates"), dataset)

    assert written.AcquisitionContextSequence[0].Date == "20260101"


def test_modified_dates_modify_an_acquisition_date():
    dataset = _enhanced_ct(_item("DATE", ACQUISITION_DATE, Date="20260101"))
    options = (CSC, "retain_longitudinal_modified_dates")

    assert _actions(options, dataset)[_path((ACQUISITION_CONTEXT, 0), tag=DATE)] == "C"
    written = _written(options, dataset)
    modified = written.AcquisitionContextSequence[0].Date
    assert modified and modified != "20260101"


def test_retain_uids_keeps_a_device_observer_uid():
    value = "1.2.826.0.1.3680043.10.188.1"
    dataset = _enhanced_ct(_item("UIDREF", DEVICE_OBSERVER_UID, UID=value))

    written = _written((CSC, "retain_uids"), dataset)

    assert written.AcquisitionContextSequence[0].UID == value
    assert not _actions((CSC,), dataset)


def test_clean_descriptors_falls_back_for_content_item_text():
    removed = _enhanced_ct(_coded(), _text(ACQUISITION_PROTOCOL))
    dummy = _enhanced_ct(_coded(), _text(FINDING_SITE))
    options = (CSC, "clean_descriptors")

    assert not _actions(options, removed)
    written = _written(options, removed, _cleaning())
    assert len(written.AcquisitionContextSequence) == 0
    written = _written(options, dummy, _cleaning())
    assert len(written.AcquisitionContextSequence) == 2
    assert written.AcquisitionContextSequence[1].TextValue


def test_an_unlisted_text_item_falls_back_under_clean_descriptors():
    written = _written(
        (CSC, "clean_descriptors"), _enhanced_ct(_coded(), _text()), _cleaning()
    )

    assert len(written.AcquisitionContextSequence) == 2
    assert written.AcquisitionContextSequence[1].TextValue


def _ct_with_specimen(*content):
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    preparation = pydicom.Dataset()
    preparation.SpecimenPreparationStepContentItemSequence = pydicom.Sequence(
        list(content)
    )
    specimen = pydicom.Dataset()
    specimen.SpecimenIdentifier = f"{SENTINEL} SPECIMEN"
    specimen.SpecimenUID = "1.2.826.0.1.3680043.10.188.2"
    specimen.SpecimenPreparationSequence = pydicom.Sequence([preparation])
    dataset.SpecimenDescriptionSequence = pydicom.Sequence([specimen])
    return dataset


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_specimen_preparation_content_items_are_cleaned():
    dataset = _ct_with_specimen(
        _coded(), _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    )
    sequence = _path(("(0040,0560)", 0), tag=SPECIMEN_PREPARATION)
    step = (("(0040,0560)", 0), (SPECIMEN_PREPARATION, 0), ("(0040,0612)", 1))

    assert dict(_actions((CSC,), dataset, "CT Image")) == {
        sequence: "K",
        _path(*step, tag=PERSON_NAME): "D",
    }
    written = _written((CSC,), dataset)
    (specimen,) = written.SpecimenDescriptionSequence
    (preparation,) = specimen.SpecimenPreparationSequence
    assert len(preparation.SpecimenPreparationStepContentItemSequence) == 2
    basic = _written((), dataset).SpecimenDescriptionSequence[0]
    assert len(basic.SpecimenPreparationSequence) == 0


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_specimen_preparation_with_an_item_to_remove_takes_its_basic_action():
    dataset = _ct_with_specimen(_coded(), _text(ACCESSION_NUMBER))

    assert not _actions((CSC,), dataset, "CT Image")
    (specimen,) = _written((CSC,), dataset).SpecimenDescriptionSequence
    assert len(specimen.SpecimenPreparationSequence) == 0


def test_a_sequence_that_the_iod_does_not_define_there_is_not_kept():
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.AcquisitionContextSequence = pydicom.Sequence([_coded()])

    assert not _actions((CSC,), dataset, "CT Image")
    assert "AcquisitionContextSequence" not in _written((CSC,), dataset)


def _container(concept, *items):
    """Return a CONTAINER content item that contains ``items``."""
    container = _item("CONTAINER", concept, ContinuityOfContent="SEPARATE")
    for item in items:
        item.RelationshipType = "CONTAINS"
    container.ContentSequence = pydicom.Sequence(list(items))
    return container


SECTION = ("SEC1", "99PMP", "Fixture section")


def _report(*items, title=("TTL1", "99PMP", "Fixture report"), depth=1):
    """Return a Structured Report whose tree holds ``items`` at ``depth``."""
    for _ in range(depth - 1):
        items = (_container(SECTION, *items),)
    dataset = _container(title, *items)
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.10.188.3"
    return dataset


def _tree(depth):
    """Return the paths of the Content Sequences down to ``depth``, outermost first."""
    return [_path(*((CONTENT, 0),) * level, tag=CONTENT) for level in range(depth)]


def _by_reference(*positions):
    item = pydicom.Dataset()
    item.RelationshipType = "INFERRED FROM"
    item.ReferencedContentItemIdentifier = list(positions)
    return item


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("depth", [1, 2, 5])
def test_content_sequence_items_are_cleaned_at_any_depth(depth):
    name = _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    dataset = _report(_coded(), name, _text(), depth=depth)
    *outer, innermost = _tree(depth)
    leaf = (*innermost.items, (CONTENT, 1))

    assert dict(_actions((CSC,), dataset, REPORT)) == {
        **{sequence: "K" for sequence in (*outer, innermost)},
        _path(*leaf, tag=PERSON_NAME): "D",
    }


@pytest.mark.parametrize(
    "dataset",
    [
        _report(_coded(), _text(ACCESSION_NUMBER), depth=3),
        # The nested Content Sequence could be kept, but not on its own.
        _report(_text(ACCESSION_NUMBER), _container(SECTION, _coded())),
    ],
)
def test_an_item_to_remove_anywhere_leaves_out_the_whole_tree(dataset):
    assert not _actions((CSC,), dataset, REPORT)


def test_the_walker_gives_content_sequence_items_their_actions():
    name = _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    source = read_source(
        synthetic.written(_report(name, _by_reference(1, 1, 1), depth=2))
    )
    iod = load_iod_tables().iods[REPORT]
    rules = ElementRules(policy.compose_custom_policy([CSC]))
    actions = content_items.content_item_actions(source, rules.policy, iod)

    planned = {e.path: e for e in plan_instance(source, rules, iod, actions).elements}

    outer, inner = _tree(2)
    for sequence in (outer, inner):
        assert planned[sequence].action == "K"
        assert planned[sequence].rule.source is RuleSource.CONTENT_ITEM
    leaf = inner.items + ((CONTENT, 0),)
    assert planned[_path(*leaf, tag=PERSON_NAME)].action == "D"
    reference = inner.items + ((CONTENT, 1),)
    assert planned[_path(*reference, tag=REFERENCED_CONTENT_ITEM)].action == "K"
    # Without the option, Table E.1-1's D leaves no dummy value for a
    # sequence, so the report is sequestered (D-021).
    without = plan_instance(source, rules, iod)
    assert [s.path for s in without.sequestrations] == [outer]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_retired_snomed_code_deep_in_a_report_takes_its_options_action():
    # G-D321 is Start DateTime, SCT 398201009: D, and K under Full Dates.
    start = _item("DATETIME", ("G-D321", "SRT", "Start"), DateTime="20260101120000")
    dataset = _report(_coded(), start, depth=3)
    *_, innermost = _tree(3)
    value = _path(*innermost.items, (CONTENT, 1), tag="(0040,A120)")

    assert _actions((CSC,), dataset, REPORT)[value] == "D"
    full_dates = (CSC, "retain_longitudinal_full_dates")
    assert _actions(full_dates, dataset, REPORT)[value] == "K"


def test_the_root_of_a_report_is_a_content_item_too():
    # Table E.3.4-1 gives this CONTAINER X, and Retain Device Identity K.
    unique_device_identifiers = ("121000", "DCM", "Unique Device Identifiers")
    dataset = _report(_coded(), title=unique_device_identifiers)

    assert not _actions((CSC,), dataset, REPORT)
    assert dict(_actions((CSC, "retain_device_identity"), dataset, REPORT)) == {
        _path(tag=CONTENT): "K"
    }


def _unnamed(item):
    del item.ConceptNameCodeSequence
    return item


def _image_reference():
    reference = pydicom.Dataset()
    reference.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    reference.ReferencedSOPInstanceUID = "1.2.826.0.1.3680043.10.188.4"
    return _item(
        "IMAGE",
        ("CTX1", "99PMP", "Fixture"),
        ReferencedSOPSequence=pydicom.Sequence([reference]),
    )


def _named_by_reference():
    item = _by_reference(1)
    item.ConceptNameCodeSequence = pydicom.Sequence([_code("CTX1", "99PMP", "Fixture")])
    return item


@pytest.mark.parametrize(
    "item",
    [
        _unnamed(_image_reference()),
        _unnamed(_container(SECTION, _coded())),
        _by_reference(1),
    ],
)
def test_an_unnamed_reference_or_a_by_reference_relationship_is_kept(item):
    actions = _actions((CSC,), _report(_coded(), item), REPORT)

    assert actions[_path(tag=CONTENT)] == "K"


@pytest.mark.parametrize(
    "item",
    [
        # PS3.3 Table C.17-5 requires a concept name for these Value Types.
        _unnamed(_text()),
        _unnamed(_item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")),
        # A by-reference relationship has no concept name.
        _named_by_reference(),
    ],
)
def test_an_item_with_a_missing_or_stray_concept_name_is_not_kept(item):
    assert not _actions((CSC,), _report(_coded(), item), REPORT)


def test_an_unnamed_root_is_not_kept():
    dataset = _report(_coded())
    del dataset.ConceptNameCodeSequence

    assert not _actions((CSC,), dataset, REPORT)


def test_a_content_sequence_the_iod_does_not_define_there_takes_its_own_rule():
    context = _coded()
    context.ContentSequence = pydicom.Sequence(
        [_item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")]
    )
    dataset = _enhanced_ct(context)

    assert dict(_actions((CSC,), dataset)) == {_path(tag=ACQUISITION_CONTEXT): "K"}
    written = _written((CSC,), dataset)
    assert "ContentSequence" not in written.AcquisitionContextSequence[0]


def test_only_the_dose_reports_define_content_sequence_and_none_waveform_annotation():
    """Content Sequence at their root, and nowhere else in a supported IOD."""
    iods = load_iod_tables().iods
    reports = {"X-Ray Radiation Dose SR", "Radiopharmaceutical Radiation Dose SR"}
    for name in scope.SUPPORTED_IODS:
        definitions = iods[name].definitions
        tags = {definition.tag for definition in definitions}
        assert WAVEFORM_ANNOTATION not in tags, name
        assert {d.path for d in definitions if d.tag == CONTENT} == (
            {()} if name in reports else set()
        ), name


def test_the_statement_describes_the_cleaning_of_content_items():
    composed = policy.compose_custom_policy([CSC])
    statement = conformance.conformance_statement(composed, vocabulary=None)
    by_tag = {entry.tag: entry for entry in statement.attributes}

    for tag in content_items.CONTENT_ITEM_SEQUENCES:
        assert by_tag[tag].action == "C"
        assert not by_tag[tag].superseded_by
    entry = by_tag[WAVEFORM_ANNOTATION]
    assert entry.superseded_by == conformance.SEQUENCE_NOT_CLEANED
    (cleaned,) = statement.cleaned
    assert cleaned.option == CSC
    assert cleaned.tags == (ACQUISITION_CONTEXT, SPECIMEN_PREPARATION, CONTENT)
    assert cleaned.method == content_items.METHOD
    assert not statement.pending
    markdown = conformance_markdown.render_markdown(statement)
    assert "which hold content items, and the engine cleans them" in markdown
    assert "since a single item is not removed on its own." in markdown
