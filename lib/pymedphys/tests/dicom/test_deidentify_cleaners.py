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

"""The cleaners that settle C, and Retain Device Identity's AE-title tokens.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import base64
import io
import re

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    ae_titles,
    cleaners,
    conformance,
    conformance_markdown,
    keys,
    run,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.edits import Edit, EditKind, InstanceEdits
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    DEVICE_IDENTITY,
    PRESETS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.standard import (
    OPTIONS,
    dictionary_attribute,
    load_table_e1_1,
)
from pymedphys._dicom.deidentify.values import values_problem

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
OTHER_KEY = DeidKey(bytes(range(1, 33)))
_TOKEN = re.compile(r"AE[A-Z2-7]{14}")
_STATION_AE = ElementPath((), "(0008,0055)")
_RETRIEVE_AE = ElementPath((), "(0008,0054)")
_ALLERGIES = ElementPath((), "(0010,2110)")
DEVICE_IDENTITY_CODE = "113109"
CLEAN_DESCRIPTORS_CODE = "113105"


def test_an_ae_token_is_a_valid_ae_value_of_16_characters():
    for value in ("CT1", "SENTINEL_AE_0001", " PADDED ", "a-b.c_d"):
        token = ae_titles.ae_token(value, KEY)

        assert _TOKEN.fullmatch(token)
        assert values_problem("AE", "1", [token]) is None
        assert "SENTINEL" not in token


def test_an_ae_token_is_the_same_for_the_same_value_once_spaces_are_removed():
    token = ae_titles.ae_token("SENTINEL_CT", KEY)

    assert ae_titles.ae_token("  SENTINEL_CT  ", KEY) == token
    assert ae_titles.ae_token("SENTINEL_MR", KEY) != token
    # Each run has its own key, so tokens are unrelated across runs.
    assert ae_titles.ae_token("SENTINEL_CT", OTHER_KEY) != token
    # Only leading and trailing spaces are insignificant in VR AE.
    assert ae_titles.ae_token("SENTINEL CT", KEY) != token


def test_an_ae_token_is_derived_as_the_conformance_statement_says():
    # `AE` and the first 14 base32 characters of the value's HMAC-SHA256 in a
    # domain of its own.
    assert ae_titles.DOMAIN in keys.DOMAINS
    derived = KEY.derive(ae_titles.DOMAIN, "SENTINEL_CT")

    assert ae_titles.ae_token(" SENTINEL_CT", KEY) == (
        "AE" + base64.b32encode(derived).decode("ascii")[:14]
    )


def test_each_value_of_an_ae_attribute_gets_its_own_token():
    tokens = ae_titles.ae_tokens("SENTINEL_A\\\\ SENTINEL_B\\SENTINEL_A", KEY)

    assert tokens == (
        ae_titles.ae_token("SENTINEL_A", KEY),
        "",
        ae_titles.ae_token("SENTINEL_B", KEY),
        ae_titles.ae_token("SENTINEL_A", KEY),
    )
    assert not ae_titles.ae_tokens("", KEY)
    assert ae_titles.ae_tokens("   ", KEY) == ("",)


def test_no_two_cleaners_clean_the_same_attribute():
    tags = [tag for cleaner in cleaners.CLEANERS for tag in cleaner.tags]

    assert len(tags) == len(set(tags))
    assert all(cleaner.option in OPTIONS for cleaner in cleaners.CLEANERS)


def test_each_cleaner_cleans_attributes_its_option_gives_c_in_the_vrs_it_reads():
    for cleaner in cleaners.CLEANERS:
        composed = compose_custom_policy([cleaner.option])
        # Table E.1-1's rows, and the supplementary rules for attributes that
        # it omits.
        actions = {**composed.actions, **composed.supplementary_actions}
        for tag in cleaner.tags:
            assert actions[tag] == "C"
            attribute = dictionary_attribute(tag)
            assert attribute is not None
            assert set(attribute.vrs) <= cleaner.vrs


@pytest.mark.deid_requirement("PS3.15-E.3.8-01")
def test_every_attribute_that_retain_device_identity_gives_c_has_a_cleaner():
    given_c = {
        row.tag
        for row in load_table_e1_1().attributes
        if row.options.get(DEVICE_IDENTITY) == "C"
    }
    cleaned = {
        tag
        for cleaner in cleaners.CLEANERS
        if cleaner.option == DEVICE_IDENTITY
        for tag in cleaner.tags
    }

    assert given_c == cleaned == ae_titles.TAGS


def test_a_policy_has_the_cleaners_of_the_options_it_selects():
    assert not cleaners.cleaners_for(compose_policy("basic"))
    (cleaner,) = cleaners.cleaners_for(compose_custom_policy([DEVICE_IDENTITY]))
    assert cleaner.option == DEVICE_IDENTITY
    assert cleaner in cleaners.cleaners_for(compose_policy("tps-import"))
    # Each preset has the cleaners of its own options, in the registry's order,
    # whichever options have cleaners.
    for preset, options in PRESETS.items():
        assert cleaners.cleaners_for(compose_policy(preset)) == tuple(
            each for each in cleaners.CLEANERS if each.option in options
        )


def _edits(*elements):
    """Edits of top-level elements, each given as path, action, kind, VR, value."""
    return InstanceEdits(
        edits=tuple(Edit(path, action, kind) for path, action, kind, _, _ in elements),
        source_values=tuple(
            SourceValue(path, vr, value)
            for path, _, _, vr, value in elements
            if value is not None
        ),
        not_collected=(),
        sequestrations=(),
    )


def test_cleaners_settle_only_the_pending_c_of_the_attributes_they_clean():
    pending = EditKind.PENDING
    edits = _edits(
        (_RETRIEVE_AE, "C", pending, "AE", "SENTINEL_PACS\\SENTINEL_CT"),
        (_STATION_AE, "C", pending, "AE", ""),
        (_ALLERGIES, "C", pending, "LO", "SENTINEL ALLERGY"),
        (ElementPath((), "(0008,1010)"), "K", EditKind.KEEP, "SH", None),
    )
    device = cleaners.cleaners_for(compose_custom_policy([DEVICE_IDENTITY]))

    cleaned = cleaners.apply_cleaners(edits, device, KEY)

    retrieve, station, allergies, kept = cleaned.edits.edits
    assert retrieve.kind is EditKind.REPLACE
    assert retrieve.values == ae_titles.ae_tokens("SENTINEL_PACS\\SENTINEL_CT", KEY)
    assert (station.kind, station.values) == (EditKind.EMPTY, ())
    # No cleaner cleans Allergies, so it stays pending.
    assert allergies == edits.edits[2]
    assert kept == edits.edits[3]
    assert cleaned.retained == frozenset()
    # The values collected for the residual search are unchanged.
    assert cleaned.edits.source_values == edits.source_values
    assert cleaners.apply_cleaners(edits, (), KEY).edits == edits


def test_a_c_whose_value_was_not_collected_or_read_in_another_vr_stays_pending():
    edits = _edits(
        (_RETRIEVE_AE, "C", EditKind.PENDING, "AE", None),
        (_STATION_AE, "C", EditKind.PENDING, "UN", b"SENTINEL"),
    )
    device = cleaners.cleaners_for(compose_custom_policy([DEVICE_IDENTITY]))

    cleaned = cleaners.apply_cleaners(edits, device, KEY)

    assert cleaned.edits.edits == edits.edits


def test_a_cleaner_that_may_write_the_source_value_leaves_it_out_of_the_search():
    keeps = cleaners.Cleaner(
        option="retain_patient_characteristics",
        tags=frozenset({"(0010,2110)"}),
        vrs=frozenset({"LO"}),
        method="Kept as it is.",
        clean=lambda source, key: (source,),
        retains=True,
    )
    edits = _edits((_ALLERGIES, "C", EditKind.PENDING, "LO", "SENTINEL"))

    cleaned = cleaners.apply_cleaners(edits, (keeps,), KEY)

    (edit,) = cleaned.edits.edits
    assert (edit.kind, edit.values) == (EditKind.REPLACE, ("SENTINEL",))
    assert cleaned.retained == frozenset({_ALLERGIES})


def test_a_cleaner_cleans_single_values_or_the_whole_instance_not_both():
    def clean(source, _key):
        return (source,)

    def clean_instance(_values, _key, _identity):
        return {}

    shared = {
        "option": "retain_patient_characteristics",
        "tags": frozenset({"(0010,2110)"}),
        "vrs": frozenset({"LO"}),
        "method": "Kept as it is.",
    }
    with pytest.raises(ValueError, match="either"):
        cleaners.Cleaner(**shared)
    with pytest.raises(ValueError, match="either"):
        cleaners.Cleaner(**shared, clean=clean, clean_instance=clean_instance)
    with pytest.raises(ValueError, match="retains"):
        cleaners.Cleaner(**shared, clean_instance=clean_instance, retains=True)


def test_a_cleaner_of_the_whole_instance_settles_what_it_returns():
    received = []
    first = ElementPath((), "(0008,0020)")
    second = ElementPath((), "(0008,0030)")
    timestamp = ElementPath((("(5200,9230)", 0),), "(0034,0007)")

    def clean_instance(values, key, identity):
        values = tuple(values)
        received.append((values, key, identity))
        return {
            first: (("19000101",), False),
            second: (("SENTINEL",), True),
            timestamp: ((b"\x00" * 10,), False),
            # A path it was not given is not settled.
            _ALLERGIES: (("NOT GIVEN",), False),
        }

    instance = cleaners.Cleaner(
        option="retain_longitudinal_modified_dates",
        tags=frozenset({"(0008,0020)", "(0008,0030)", "(0034,0007)", "(0010,2110)"}),
        vrs=frozenset({"DA", "TM", "OB"}),
        method="Modified.",
        clean_instance=clean_instance,
    )
    pending = EditKind.PENDING
    edits = _edits(
        (first, "C", pending, "DA", "SENTINEL"),
        (second, "C", pending, "TM", "SENTINEL"),
        (timestamp, "C", pending, "OB", b"SENTINEL!!"),
        # Read in a VR that the cleaner does not read, so not given to it.
        (_ALLERGIES, "C", pending, "LO", "SENTINEL"),
    )
    identity = SubjectIdentity.from_patient_id("SENTINEL")

    cleaned = cleaners.apply_cleaners(edits, (instance,), KEY, identity)

    ((given, key, subject),) = received
    assert [value.source for value in given] == [first, second, timestamp]
    assert (key, subject) == (KEY, identity)
    date, time, stamp, allergies = cleaned.edits.edits
    assert (date.kind, date.values) == (EditKind.REPLACE, ("19000101",))
    assert (time.kind, time.values) == (EditKind.REPLACE, ("SENTINEL",))
    assert (stamp.kind, stamp.values) == (EditKind.REPLACE, (b"\x00" * 10,))
    assert allergies == edits.edits[3]
    assert cleaned.retained == frozenset({second})


def test_a_cleaner_of_the_whole_instance_is_given_nothing_without_pending_c():
    def clean_instance(_values, _key, _identity):
        raise AssertionError("not called")

    instance = cleaners.Cleaner(
        option="retain_longitudinal_modified_dates",
        tags=frozenset({"(0008,0020)"}),
        vrs=frozenset({"DA"}),
        method="Modified.",
        clean_instance=clean_instance,
    )
    edits = _edits((ElementPath((), "(0008,0020)"), "K", EditKind.KEEP, "DA", None))

    assert cleaners.apply_cleaners(edits, (instance,), KEY).edits == edits


def _transform(options, cleaning=None):
    return InstanceTransform(
        compose_custom_policy(options), KEY, cleaning=cleaning, unvalidated_policy=True
    )


def _plan(**attributes):
    plan = synthetic.rt_plan()
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _written(transform, dataset):
    data = synthetic.written(dataset)
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


@pytest.mark.deid_requirement("PS3.15-E.3.8-01", "MIDI-BP-04")
def test_retain_device_identity_keeps_the_device_and_tokenises_ae_titles():
    plan = _plan(
        StationAETitle="SENTINEL_CT ",
        RetrieveAETitle=["SENTINEL_PACS", "", "SENTINEL_CT"],
        StationName="SENTINEL STATION",
        DeviceSerialNumber="SENTINEL 0001",
    )

    written = _written(_transform([DEVICE_IDENTITY]), plan)

    token = ae_titles.ae_token("SENTINEL_CT", KEY)
    assert written.StationAETitle == token
    assert list(written.RetrieveAETitle) == [
        ae_titles.ae_token("SENTINEL_PACS", KEY),
        "",
        token,
    ]
    # The device's identity, which the Basic Profile removes, is kept.
    assert written.StationName == "SENTINEL STATION"
    assert written.DeviceSerialNumber == "SENTINEL 0001"
    assert _codes(written) == ["113100", DEVICE_IDENTITY_CODE]

    basic = _written(
        InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True), plan
    )
    assert "StationAETitle" not in basic
    assert basic.get("StationName", "") != "SENTINEL STATION"


def test_an_ae_title_has_one_token_in_every_instance_of_a_run():
    transform = _transform([DEVICE_IDENTITY])
    first = _written(transform, _plan(StationAETitle="SENTINEL_CT"))
    second = _written(
        transform, _plan(PerformedStationAETitle="SENTINEL_CT", StationAETitle="X")
    )

    assert first.StationAETitle == second.PerformedStationAETitle
    assert second.StationAETitle != first.StationAETitle


def test_an_empty_ae_title_is_written_empty():
    plan = _plan()
    plan.add_new(0x00080055, "AE", "")

    written = _written(_transform([DEVICE_IDENTITY]), plan)

    assert written[0x00080055].value in ("", None)


@pytest.mark.deid_requirement("PS3.15-E.3.8-01")
def test_ae_titles_are_cleaned_before_descriptors_fall_back():
    cleaning = DescriptorCleaning(None, ReviewedNames.empty())
    plan = _plan(StationAETitle="SENTINEL_CT", StudyDescription="SENTINEL STUDY")

    written = _written(
        _transform([DEVICE_IDENTITY, "clean_descriptors"], cleaning), plan
    )

    assert written.StationAETitle == ae_titles.ae_token("SENTINEL_CT", KEY)
    assert "SENTINEL" not in str(written.get("StudyDescription", ""))
    # The options' codes follow the profile's, in Table E.1-1's order.
    assert _codes(written) == ["113100", DEVICE_IDENTITY_CODE, CLEAN_DESCRIPTORS_CODE]


def test_a_retain_c_that_no_cleaner_settles_holds_the_instance(monkeypatch):
    monkeypatch.setattr(cleaners, "CLEANERS", ())
    plan = _plan(Allergies="SENTINEL ALLERGY")
    data = synthetic.written(plan)

    result = _transform(["retain_patient_characteristics"])(
        data, InstanceRecord.from_file(data)
    )

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


def test_a_transform_gives_a_cleaner_of_the_whole_instance_its_subject(monkeypatch):
    received = []

    def clean_instance(values, _key, identity):
        received.append(identity)
        return {value.source: (("CLEANED",), False) for value in values}

    instance = cleaners.Cleaner(
        option="retain_patient_characteristics",
        tags=frozenset({_ALLERGIES.tag}),
        vrs=frozenset({"LO"}),
        method="Cleaned.",
        clean_instance=clean_instance,
    )
    monkeypatch.setattr(cleaners, "CLEANERS", (instance,))
    data = synthetic.written(_plan(Allergies="SENTINEL ALLERGY"))
    record = InstanceRecord.from_file(data)

    result = _transform(["retain_patient_characteristics"])(data, record)

    assert isinstance(result, run.Transformed), result
    assert record.patient is not None
    assert received == [record.patient]
    assert pydicom.dcmread(io.BytesIO(result.data)).Allergies == "CLEANED"


def test_the_statement_gives_each_cleaners_method_and_needs_no_other():
    composed = compose_custom_policy([DEVICE_IDENTITY])
    (cleaner,) = cleaners.cleaners_for(composed)
    statement = conformance.conformance_statement(composed, vocabulary=None)

    (cleaned,) = statement.cleaned
    assert cleaned == conformance.CleanedAttributes(
        DEVICE_IDENTITY, tuple(sorted(ae_titles.TAGS)), cleaner.method
    )
    assert conformance.PENDING_CLEANING not in statement.pending
    text = conformance_markdown.render_markdown(statement)
    section = text.split("## Cleaning under the Retain Device Identity Option")[1]
    section = section.split("\n## ")[0]
    assert "Station AE Title (0008,0055)" in section
    assert cleaner.method in section


@pytest.mark.parametrize(
    "preset",
    [
        preset
        for preset, options in PRESETS.items()
        if not any(cleaner.option in options for cleaner in cleaners.CLEANERS)
    ],
)
def test_a_policy_without_a_cleaners_option_describes_no_cleaner(preset):
    statement = conformance.conformance_statement(
        compose_policy(preset), vocabulary=None
    )

    assert not statement.cleaned
    assert "## Cleaning under" not in conformance_markdown.render_markdown(statement)


def test_a_statement_awaits_the_cleaning_that_no_cleaner_describes(monkeypatch):
    composed = compose_policy("tps-import")
    # With Retain Device Identity's cleaner alone, tps-import's dates and
    # retained patient characteristics have no cleaner.
    monkeypatch.setattr(
        cleaners,
        "CLEANERS",
        cleaners.cleaners_for(compose_custom_policy([DEVICE_IDENTITY])),
    )

    statement = conformance.conformance_statement(composed, vocabulary=None)

    assert [cleaned.option for cleaned in statement.cleaned] == [DEVICE_IDENTITY]
    assert conformance.PENDING_CLEANING in statement.pending
