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

"""Supplementary rows for content items whose concepts Table E.3.4-1 omits.

The rows give the patient characteristics that PS3.16 2026d's templates code
under concepts that the table omits, a device's UDI as a CODE, and Subject ID
as a CODE, the actions of the attributes that hold the same information
(D-047). The reports are
synthetic, built from the templates of PS3.16 2026d by
:mod:`._synthetic_dose_reports` and :mod:`._synthetic_structured_reports`,
and each coded value added here is one of the context group that its row
names.
"""

import io
import types

from pymedphys._imports import pydicom, pytest, tomlkit

from pymedphys._dicom.deidentify import (
    content_items,
    policy,
    run,
    scope,
    structured_content,
    supplementary_concepts,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_dose_reports as dose_reports
from . import _synthetic_references as synthetic
from . import _synthetic_structured_reports as reports

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
RPC = policy.PATIENT_CHARACTERISTICS
RDI = policy.DEVICE_IDENTITY
CONTENT = "(0040,A730)"
PRESETS = ("basic", "basic-clean-descriptors", "tps-import", "public-release")
# Every option of Table E.1-1 that can be selected with the others, with
# Full Dates, which Retain Device Identity does not conflict with.
EVERY_OPTION = (
    CSC,
    policy.SAFE_PRIVATE,
    policy.UIDS,
    policy.DEVICE_IDENTITY,
    policy.INSTITUTION_IDENTITY,
    RPC,
    policy.FULL_DATES,
    policy.CLEAN_DESCRIPTORS,
)

SUBJECT_ID_CODE = ("DCM", "121030", "CODE")
PATIENT_STATE_CODE = ("DCM", "109054", "CODE")
SEX_PARAMETERS = ("DCM", "131233", "CODE")
SEX_PARAMETERS_COMMENT = ("DCM", "131234", "TEXT")
SEX_PARAMETERS_REFERENCE = ("DCM", "131235", "TEXT")
RACIAL_GROUP = ("SCT", "415229000", "CODE")
PREGNANCY = ("SCT", "364320009", "CODE")
SMOKING = ("SCT", "365981007", "CODE")
BODY_MASS_INDEX = ("SCT", "60621009", "NUM")
UDI = ("DCM", "128739", "CODE")
# The rows that Retain Patient Characteristics keeps, and those that are
# removed under every option.
KEPT_WITH_CHARACTERISTICS = (
    PATIENT_STATE_CODE,
    SEX_PARAMETERS,
    SEX_PARAMETERS_REFERENCE,
    RACIAL_GROUP,
    PREGNANCY,
    SMOKING,
)
REMOVED_UNDER_EVERY_OPTION = (
    SUBJECT_ID_CODE,
    SEX_PARAMETERS_COMMENT,
    BODY_MASS_INDEX,
)
# The row that Retain Device Identity keeps.
KEPT_WITH_DEVICE_IDENTITY = (UDI,)

# Each concept that a template of PS3.16 2026d uses with a Value Type under
# which Table E.3.4-1 does not list it, by its key and the Value Types that
# the table lists, with the templates that use it so, read from PS3.16
# 2026d.
VALUE_TYPE_MISMATCHES = {
    ("DCM", "109054", "CODE"): ("TEXT",),  # Patient State, 9 templates
    ("DCM", "109056", "CODE"): ("TEXT",),  # Stress Protocol, TID 3301, 3401
    ("DCM", "111516", "CODE"): ("TEXT",),  # Medication Type, TID 3802, 4301, 8131
    ("DCM", "111703", "CODE"): ("TEXT",),  # Processing step description, TID 8001
    # X-Ray Radiation Dose Report, the root of TID 10001, 10011, and 10040.
    ("DCM", "113701", "CONTAINER"): ("COMPOSITE",),
    # Identification of the X-Ray Source, TID 10054 row 4.
    ("DCM", "113832", "NUM"): ("TEXT",),
    ("DCM", "121030", "CODE"): ("TEXT",),  # Subject ID, TID 1007 row 3
    ("DCM", "121065", "CODE"): ("TEXT",),  # Procedure Description, TID 3809
    ("DCM", "121071", "CODE"): ("TEXT",),  # Finding, 31 templates
    # Best illustration of finding, TID 3909.
    ("DCM", "121080", "SCOORD"): ("IMAGE", "WAVEFORM"),
    ("DCM", "121080", "TCOORD"): ("IMAGE", "WAVEFORM"),
    # Source of Measurement, TID 2121, 3530, and 3715.
    ("DCM", "121112", "COMPOSITE"): ("IMAGE", "WAVEFORM"),
    ("DCM", "121112", "TCOORD"): ("IMAGE", "WAVEFORM"),
    ("DCM", "122083", "CODE"): ("TEXT",),  # Drug administered, TID 8131, 11004
    ("DCM", "122177", "CODE"): ("TEXT",),  # Procedure Result, 4 templates
    ("DCM", "125203", "CODE"): ("TEXT",),  # Acquisition Protocol, 6 templates
    ("DCM", "131563", "CODE"): ("TEXT",),  # Series Description, TID 1602
    # Complication of Procedure, 4 templates.
    ("SCT", "116224001", "CODE"): ("TEXT",),
    ("SCT", "271921002", "CODE"): ("TEXT",),  # ECG Finding, 4 templates
    ("SCT", "363698007", "CODE"): ("TEXT",),  # Finding Site, 49 templates
}

# Values from the context groups that the rows below name.
LOW_THYROID_UPTAKE = dose_reports.Code("113561", "DCM", "Low Thyroid Uptake")
FEMALE_TYPICAL = reports.Code("131230", "DCM", "Female-typical")  # CID 7459
ASIAN_RACE = reports.Code("413582008", "SCT", "Asian race")  # CID 6099
KILOGRAM_PER_SQUARE_METRE = dose_reports.Code("kg/m2", "UCUM", "kg/m2")


def _rows():
    return {
        concept.key: concept
        for concept in supplementary_concepts.load_supplementary_concepts().concepts
    }


def _code(key):
    designator, value, _ = key
    return value, designator


@pytest.fixture(name="with_option")
def _with_option(monkeypatch):
    """Return a function that composes a preset's policy with the option added."""
    monkeypatch.setattr(
        policy,
        "PRESETS",
        types.MappingProxyType(
            {preset: (*options, CSC) for preset, options in policy.PRESETS.items()}
        ),
    )
    return policy.compose_policy


@pytest.fixture(name="supported")
def _supported(monkeypatch):
    """Add the two report IODs to the supported ones, as supporting them would."""
    monkeypatch.setattr(
        scope,
        "SUPPORTED_IODS",
        scope.SUPPORTED_IODS
        | {dose_reports.RADIOPHARMACEUTICAL_IOD, reports.COMPREHENSIVE_SR_IOD},
    )


def _composed(with_option, preset, options):
    return (
        with_option(preset)
        if options is None
        else policy.compose_custom_policy(options)
    )


def _kept(dataset, iod, composed):
    """Return whether the option keeps every item of the report's content tree.

    An item that it does not keep is removed on its own, so the tree itself
    is kept either way.
    """
    source = read_source(synthetic.written(dataset))
    actions = content_items.content_item_actions(
        source, composed, load_iod_tables().iods[iod]
    )
    assert actions.get(ElementPath((), CONTENT)) == "K"
    return not (actions.removed_items or actions.emptied)


def _transformed(composed, dataset):
    data = synthetic.written(dataset)
    record = InstanceRecord.from_file(data)
    cleaning = (
        DescriptorCleaning(None, ReviewedNames.empty())
        if policy.CLEAN_DESCRIPTORS in composed.options
        else None
    )
    transform = InstanceTransform(
        composed, KEY, cleaning=cleaning, unvalidated_policy=True
    )
    # Under tps-import, the subject's synthetic birth date is chosen first.
    transform.prepare({0: record}, [data].__getitem__)
    return transform(data, record)


def test_the_shipped_rows_cover_the_concepts_that_the_table_omits():
    loaded = supplementary_concepts.load_supplementary_concepts()

    assert loaded.edition == structured_content.load_table_e3_4_1().edition
    assert loaded.acknowledgement == f"DICOM PS3.16 {loaded.edition}, © NEMA"
    assert set(_rows()) == {
        *KEPT_WITH_CHARACTERISTICS,
        *REMOVED_UNDER_EVERY_OPTION,
        *KEPT_WITH_DEVICE_IDENTITY,
    }
    listed = {c.key for c in structured_content.load_table_e3_4_1().concepts}
    assert not listed & set(_rows())
    assert all(row.note.strip() for row in _rows().values())


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, (CSC,)),
    (None, (CSC, RPC)),
    (None, (CSC, RDI)),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_each_row_takes_the_actions_of_its_attribute(with_option, preset, options):
    composed = _composed(with_option, preset, options)
    actions = content_items.concept_actions(composed.options)
    retained = RPC in composed.options

    for key in KEPT_WITH_CHARACTERISTICS:
        assert actions[key] == ("K" if retained else "X"), key
    for key in KEPT_WITH_DEVICE_IDENTITY:
        assert actions[key] == ("K" if RDI in composed.options else "X"), key
    for key in REMOVED_UNDER_EVERY_OPTION:
        assert actions[key] == "X", key


def test_only_subject_id_and_patient_state_of_the_value_type_mismatches_have_rows():
    table = {c.key for c in structured_content.load_table_e3_4_1().concepts}
    actions = content_items.concept_actions(EVERY_OPTION)

    assert len(VALUE_TYPE_MISMATCHES) == 20
    for key, listed in VALUE_TYPE_MISMATCHES.items():
        designator, value, _ = key
        assert key not in table, key
        assert {vt for d, v, vt in table if (d, v) == (designator, value)} == set(
            listed
        ), key
    with_rows = {key for key in VALUE_TYPE_MISMATCHES if key in actions}
    # Subject ID's CODE holds the identifier; a coded Patient State is a
    # patient characteristic. The other 18 hold codes from coding schemes,
    # numbers, coordinates, references, or no value, which an unlisted item
    # keeps or whose UIDs take their own rules.
    assert with_rows == {SUBJECT_ID_CODE, PATIENT_STATE_CODE}


def _radiopharmaceutical(*characteristics):
    """Return a radiopharmaceutical dose report with ``characteristics``.

    They are the items of TID 10021 row 5, TID 10024, which is included only
    with at least one of them; the report holds its required rows otherwise.
    """
    dataset = dose_reports.radiopharmaceutical_dose_report(())
    if characteristics:
        dataset.ContentSequence.append(
            dose_reports.item(
                "CONTAINS",
                "CONTAINER",
                dose_reports.PATIENT_CHARACTERISTICS,
                *characteristics,
            )
        )
    return dataset


def _patient_state():
    # TID 10024 row 2, from CID 10045.
    return dose_reports.item(
        "CONTAINS",
        "CODE",
        dose_reports.Code(*_code(PATIENT_STATE_CODE), "Patient state"),
        code=LOW_THYROID_UPTAKE,
    )


def _body_mass_index():
    # TID 10024 row 9.
    return dose_reports.item(
        "CONTAINS",
        "NUM",
        dose_reports.Code(*_code(BODY_MASS_INDEX), "Body Mass Index"),
        number="26.1",
        units=KILOGRAM_PER_SQUARE_METRE,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options, kept", [
    (None, (CSC,), False),
    (None, (CSC, RPC), True),
    ("public-release", None, False),
    ("tps-import", None, True),
    (None, EVERY_OPTION, True),
])  # fmt: skip
def test_a_coded_patient_state_in_a_dose_report_is_kept_only_with_the_characteristics(
    with_option, preset, options, kept
):
    composed = _composed(with_option, preset, options)
    iod = dose_reports.RADIOPHARMACEUTICAL_IOD

    assert _kept(_radiopharmaceutical(), iod, composed)
    assert _kept(_radiopharmaceutical(_patient_state()), iod, composed) is kept


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", [
    ("tps-import", None),
    ("public-release", None),
    (None, (CSC, RPC)),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_body_mass_index_in_a_dose_report_is_removed_on_its_own(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    iod = dose_reports.RADIOPHARMACEUTICAL_IOD

    assert _kept(_radiopharmaceutical(), iod, composed)
    assert not _kept(_radiopharmaceutical(_body_mass_index()), iod, composed)


@pytest.mark.usefixtures("supported")
def test_tps_import_writes_a_coded_patient_state_that_it_keeps(with_option):
    dataset = _radiopharmaceutical(_patient_state())

    result = _transformed(with_option("tps-import"), dataset)

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    (characteristics,) = (
        item
        for item in written.ContentSequence
        if item.ConceptNameCodeSequence[0].CodeValue == "121118"
    )
    codes = {
        item.ConceptCodeSequence[0].CodeValue
        for item in characteristics.ContentSequence
        if item.ValueType == "CODE"
    }
    assert codes == {LOW_THYROID_UPTAKE.value}


def _subject(key, meaning, **value):
    """Return a TID 1007 item of the concept ``key`` for an imaging report."""
    return reports.item(
        reports.OBSERVATION,
        key[2],
        reports.Code(*_code(key), meaning),
        **value,
    )


UDI_TEXT = "SENTINEL-UDI-(01)00000000000000(21)FIXTURE"


def _udi():
    """Return TID 11004 row 26, a UDI as a CODE, beside an imaging report's items.

    TID 11004 names no coding scheme for the identifier, so the code is in a
    local one, and the identifier, longer than a Code Value, is its Long Code
    Value (0008,0119).
    """
    udi = reports.item(
        "CONTAINS",
        "CODE",
        reports.Code(*_code(UDI), "UDI"),
        code=reports.Code("UDI1", "99PMP", "Syringe UDI"),
    )
    code = udi.ConceptCodeSequence[0]
    del code.CodeValue
    code.LongCodeValue = UDI_TEXT
    return udi


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, (CSC,)),
    (None, (CSC, RDI)),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_udi_is_kept_only_with_device_identity(with_option, preset, options):
    composed = _composed(with_option, preset, options)
    iod = reports.COMPREHENSIVE_SR_IOD
    characteristics = RPC in composed.options

    # The imaging report's sex, TID 1007 row 5, is kept only with the
    # characteristics, as the rows above show.
    assert _kept(_imaging(), iod, composed) is characteristics
    assert _kept(_imaging(_udi()), iod, composed) is (
        characteristics and RDI in composed.options
    )


@pytest.mark.usefixtures("supported")
def test_a_written_report_holds_no_udi_without_device_identity():
    result = _transformed(policy.compose_custom_policy((CSC,)), _imaging(_udi()))

    assert isinstance(result, run.Transformed), result
    assert UDI_TEXT.encode() not in result.data
    assert b"SENTINEL" not in result.data


def _imaging(*extra):
    dataset = reports.imaging_report(("TID 1007 row 5",))
    dataset.ContentSequence.extend(extra)
    return dataset


SUBJECT_ROWS = {
    "TID 1007 row 5a": (
        SEX_PARAMETERS,
        lambda: _subject(
            SEX_PARAMETERS,
            "Subject Sex Parameters for Clinical Use Category",
            code=FEMALE_TYPICAL,
        ),
    ),
    "TID 1007 row 5b": (
        SEX_PARAMETERS_COMMENT,
        lambda: _subject(
            SEX_PARAMETERS_COMMENT,
            "Subject Sex Parameters for Clinical Use Category Comment",
            text=f"{reports.SENTINEL} COMMENT",
        ),
    ),
    "TID 1007 row 5c": (
        SEX_PARAMETERS_REFERENCE,
        lambda: _subject(
            SEX_PARAMETERS_REFERENCE,
            "Subject Sex Parameters for Clinical Use Category Reference",
            text=f"{reports.SENTINEL} REFERENCE",
        ),
    ),
    "TID 1007 row 9": (
        RACIAL_GROUP,
        lambda: _subject(RACIAL_GROUP, "Racial group", code=ASIAN_RACE),
    ),
    "TID 1007 row 3": (SUBJECT_ID_CODE, reports.subject_identifier),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("row", SUBJECT_ROWS)
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, (CSC,)),
    (None, (CSC, RPC)),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_each_subject_row_is_kept_only_where_its_attribute_is(
    with_option, row, preset, options
):
    composed = _composed(with_option, preset, options)
    key, build = SUBJECT_ROWS[row]
    iod = reports.COMPREHENSIVE_SR_IOD
    expected = key in KEPT_WITH_CHARACTERISTICS and RPC in composed.options

    # Subject Sex, row 5, takes Retain Patient Characteristics' K too.
    assert _kept(_imaging(), iod, composed) is (RPC in composed.options)
    assert _kept(_imaging(build()), iod, composed) is expected


def _document(**changes):
    document = {
        "schema": supplementary_concepts.SCHEMA,
        "edition": "2026d",
        "acknowledgement": "DICOM PS3.16 2026d, © NEMA",
        "concept": [
            {
                "scheme_designator": "99PMP",
                "code_value": "FIX1",
                "value_type": "CODE",
                "code_meaning": "Fixture",
                "basic_profile": "X",
                "options": {"retain_patient_characteristics": "K"},
                "note": "A fixture.",
            }
        ],
    }
    document.update(changes)
    return document


def _row_with(**changes):
    (row,) = _document()["concept"]
    row.update(changes)
    return _document(concept=[row])


def _without(field):
    (row,) = _document()["concept"]
    del row[field]
    return _document(concept=[row])


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def test_a_valid_file_loads(tmp_path):
    path = _write(tmp_path / "concepts.toml", _document())

    (row,) = supplementary_concepts.load_supplementary_concepts(path).concepts

    assert row.key == ("99PMP", "FIX1", "CODE")
    assert dict(row.options) == {"retain_patient_characteristics": "K"}


@pytest.mark.parametrize("document, message", [
    (_document(schema="other/1"), "schema"),
    (_document(edition="2026c"), "edition of Table E.3.4-1"),
    (_document(acknowledgement="DICOM"), "acknowledgement"),
    (_document(concept={"a": 1}), "array of tables"),
    (_without("note"), "exactly the fields"),
    (_row_with(extra="1"), "exactly the fields"),
    (_row_with(scheme_designator="9 9"), "coding scheme designator"),
    (_row_with(code_value="X" * 17), "code value"),
    (_row_with(value_type="NUMERIC"), "value type"),
    (_row_with(code_meaning=""), "code meaning"),
    (_row_with(basic_profile="K"), "X as its Basic Profile action"),
    (_row_with(note=" "), "note"),
    (_row_with(options={}), "table of option actions"),
    (_row_with(options={"clean_descriptors": "C"}), "under clean_descriptors"),
    (
        _row_with(options={"retain_patient_characteristics": "C"}),
        "other than K",
    ),
    (_row_with(options={"retain_device_identity": "C"}), "other than K"),
    # Subject ID as TEXT is a row of Table E.3.4-1.
    (
        _row_with(scheme_designator="DCM", code_value="121030", value_type="TEXT"),
        "listed in Table E.3.4-1",
    ),
    (_document(concept=_document()["concept"] * 2), "repeats"),
])  # fmt: skip
def test_a_file_that_cannot_be_used_is_refused(tmp_path, document, message):
    path = _write(tmp_path / "concepts.toml", document)

    with pytest.raises(supplementary_concepts.SupplementaryConceptError, match=message):
        supplementary_concepts.load_supplementary_concepts(path)


def test_an_unreadable_file_is_refused(tmp_path):
    path = tmp_path / "concepts.toml"
    path.write_text("schema = [", encoding="utf-8")

    with pytest.raises(supplementary_concepts.SupplementaryConceptError, match="read"):
        supplementary_concepts.load_supplementary_concepts(path)
