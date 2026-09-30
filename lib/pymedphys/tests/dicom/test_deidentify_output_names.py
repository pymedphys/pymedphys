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

"""Output names built only from replacement identifiers."""

import inspect
import pathlib
import re
import uuid

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import keys, output_names, pseudonyms, uids

st = hypothesis.strategies

# An invented key and instance: its source path, identifiers, and UIDs under
# the invented root 1.2.840.99999.
FIXTURE_KEY = keys.DeidKey(bytes(range(32)))
SOURCE_PATH = "fixture-archive/FIXTURE^PATIENT/MRN0001/CT 2026-01-02/IMG00042.dcm"
SOURCE_ISSUER = "FIXTURE HOSPITAL"
SOURCE_NAME = "FIXTURE^PATIENT"
SOURCE = {
    "patient_id": "MRN0001",
    "study": "1.2.840.99999.2.55.3.604688119.868.1234567888",
    "series": "1.2.840.99999.2.55.3.604688119.868.1234567889",
    "sop": "1.2.840.99999.2.55.3.604688119.868.1234567890.1",
}
# The replacements of the invented values under the invented key.
PSEUDONYM = "DEID-3IG6TYZOJUCGHKBY"
REPLACEMENT_UID = "2.25.45880388381039869122547204841297202992"
REPLACEMENT_NUMBER = int(REPLACEMENT_UID.removeprefix("2.25."))

UID_ATTRIBUTES = {
    "study_instance_uid": "Study Instance UID",
    "series_instance_uid": "Series Instance UID",
    "sop_instance_uid": "SOP Instance UID",
}
# Windows reserves these device names, also when an extension follows.
RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"{device}{suffix}" for device in ("COM", "LPT") for suffix in "0123456789¹²³"}
)

any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)
# Source UIDs under the invented root, which no "2.25." name can contain.
source_uids = st.from_regex(
    r"1\.2\.840\.99999(?:\.(?:0|[1-9][0-9]{0,9})){1,8}", fullmatch=True
)
# Source Patient IDs with a lower-case letter other than d, c, and m, the only
# lower-case letters an output path can contain.
source_patient_ids = st.from_regex(
    r"[A-Za-z0-9 ]{0,10}[abe-ln-z][A-Za-z0-9 ]{0,10}", fullmatch=True
)
padding = st.text(alphabet="\x00 ", min_size=1, max_size=3)


def _replacements(key, patient_id, study, series, sop):
    identity = pseudonyms.SubjectIdentity.from_patient_id(patient_id, SOURCE_ISSUER)
    return {
        "patient_id": pseudonyms.patient_pseudonym(key, identity).patient_id,
        "study_instance_uid": uids.replacement_uid(key, study),
        "series_instance_uid": uids.replacement_uid(key, series),
        "sop_instance_uid": uids.replacement_uid(key, sop),
    }


def _path(key, **source):
    return output_names.instance_path(**_replacements(key, **{**SOURCE, **source}))


def _uid(number):
    return f"2.25.{number}"


def test_a_path_is_built_from_the_replacement_identifiers():
    identity = pseudonyms.SubjectIdentity.from_patient_id("MRN0001", SOURCE_ISSUER)
    pseudonym = pseudonyms.patient_pseudonym(FIXTURE_KEY, identity)
    study, series, sop = (
        uids.replacement_uid(FIXTURE_KEY, SOURCE[level])
        for level in ("study", "series", "sop")
    )

    assert _path(FIXTURE_KEY) == pathlib.PurePosixPath(
        pseudonym.patient_id, study, series, sop + ".dcm"
    )


def test_paths_are_pinned():
    # A changed layout would rename every file of an incremental export.
    assert _path(FIXTURE_KEY) == pathlib.PurePosixPath(
        "DEID-3IG6TYZOJUCGHKBY",
        "2.25.11262718090212835546193287475578310451",
        "2.25.43083933323976095859471764867716168708",
        "2.25.45880388381039869122547204841297202992.dcm",
    )


def test_no_source_path_file_name_or_value_appears_in_a_path():
    text = str(_path(FIXTURE_KEY)).casefold()
    source_path = pathlib.PurePosixPath(SOURCE_PATH)
    fragments = [
        *source_path.parts,
        source_path.stem,
        SOURCE_ISSUER,
        SOURCE_NAME,
        *SOURCE.values(),
    ]

    for fragment in fragments:
        assert fragment.casefold() not in text
    assert "anonym" not in text


@hypothesis.given(any_key, source_patient_ids, source_uids, source_uids, source_uids)
def test_no_source_value_appears_in_any_path(key, patient_id, study, series, sop):
    text = str(_path(key, patient_id=patient_id, study=study, series=series, sop=sop))

    for value in (patient_id.strip(), study, series, sop):
        assert value not in text


def test_only_replacement_identifiers_are_accepted():
    parameters = inspect.signature(output_names.instance_path).parameters

    assert list(parameters) == [
        "patient_id",
        "study_instance_uid",
        "series_instance_uid",
        "sop_instance_uid",
    ]
    for parameter in parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        # pylint: disable-next = too-many-function-args, missing-kwoa
        output_names.instance_path(*_replacements(FIXTURE_KEY, **SOURCE).values())


def _variant_changed(number, variant_bits):
    """Return ``number`` with its three UUID variant bits replaced."""
    return number & ~(0b111 << 61) | variant_bits << 61


NOT_PATIENT_IDS = {
    "source-id": "MRN0001",
    "lower-case-code": "DEID-3ig6tyzojucghkby",
    "lower-case-prefix": "deid-3IG6TYZOJUCGHKBY",
    "other-prefix": "SUBJ-3IG6TYZOJUCGHKBY",
    "15-characters": "DEID-3IG6TYZOJUCGHKB",
    "17-characters": "DEID-3IG6TYZOJUCGHKBYA",
    "zero-in-code": "DEID-3IG6TYZOJUCGHKB0",
    "one-in-code": "DEID-3IG6TYZOJUCGHKB1",
    "patients-name": "DEIDENTIFIED^3IG6TYZOJUCGHKBY",
    "empty": "",
    "none": None,
    "bytes": PSEUDONYM.encode("ascii"),
    "multi-value": [PSEUDONYM, PSEUDONYM],
}
NOT_REPLACEMENT_UIDS = {
    "source-uid": SOURCE["sop"],
    "registered-sop-class": "1.2.840.10008.5.1.4.1.1.2",
    "64-characters": "1.2.840.99999." + "1" * 50,
    "version-4": _uid(uuid.UUID(int=REPLACEMENT_NUMBER, version=4).int),
    "ncs-variant": _uid(_variant_changed(REPLACEMENT_NUMBER, 0b010)),
    "microsoft-variant": _uid(_variant_changed(REPLACEMENT_NUMBER, 0b110)),
    "future-variant": _uid(_variant_changed(REPLACEMENT_NUMBER, 0b111)),
    "leading-zero": _uid(f"0{REPLACEMENT_NUMBER}"),
    "2-to-the-128": _uid(2**128),
    "5000-digits": _uid("1" * 5000),
    "zero": _uid(0),
    "root-only": "2.25.",
    "two-components": "2.25.1.2",
    "other-root": "2.26." + str(REPLACEMENT_NUMBER),
    "full-width-digit": REPLACEMENT_UID[:-1] + "\N{FULLWIDTH DIGIT TWO}",
    "underscore": REPLACEMENT_UID[:10] + "_" + REPLACEMENT_UID[10:],
    "line-feed": REPLACEMENT_UID + "\n",
    "empty": "",
    "none": None,
    "bytes": REPLACEMENT_UID.encode("ascii"),
    "multi-value": [REPLACEMENT_UID, REPLACEMENT_UID],
}
NOT_REPLACEMENTS = [
    pytest.param("patient_id", "Patient ID", value, id=f"patient_id-{label}")
    for label, value in NOT_PATIENT_IDS.items()
] + [
    pytest.param(attribute, name, value, id=f"{attribute}-{label}")
    for attribute, name in UID_ATTRIBUTES.items()
    for label, value in NOT_REPLACEMENT_UIDS.items()
]


@pytest.mark.parametrize("attribute, name, value", NOT_REPLACEMENTS)
def test_a_value_that_is_not_a_replacement_names_nothing(attribute, name, value):
    arguments = _replacements(FIXTURE_KEY, **SOURCE)
    arguments[attribute] = value

    with pytest.raises(output_names.OutputNameError) as raised:
        output_names.instance_path(**arguments)

    message = str(raised.value)
    assert name in message
    if value:
        assert str(value) not in message
        assert repr(value) not in message


@hypothesis.given(
    st.binary(min_size=32, max_size=32),
    source_patient_ids,
    st.lists(source_uids, min_size=3, max_size=3),
    st.lists(padding, min_size=4, max_size=4),
)
def test_a_path_depends_only_on_the_replacement_values(
    secret, patient_id, source, pads
):
    study, series, sop = source
    arguments = _replacements(keys.DeidKey(secret), patient_id, study, series, sop)
    padded = {
        attribute: value + pad
        for (attribute, value), pad in zip(arguments.items(), pads, strict=True)
    }

    assert output_names.instance_path(**padded) == _path(
        keys.DeidKey(secret), patient_id=patient_id, study=study, series=series, sop=sop
    )


@hypothesis.given(
    st.lists(st.binary(min_size=32, max_size=32), min_size=2, max_size=2, unique=True)
)
def test_a_new_key_gives_unrelated_names(secrets):
    first, second = (_path(keys.DeidKey(secret)) for secret in secrets)

    for first_part, second_part in zip(first.parts, second.parts, strict=True):
        assert first_part != second_part


def test_instances_of_one_series_share_its_directories():
    first = _path(FIXTURE_KEY, sop=SOURCE["sop"])
    second = _path(FIXTURE_KEY, sop=SOURCE["sop"] + "0")
    other_series = _path(FIXTURE_KEY, series=SOURCE["series"] + "0", sop="1.2.3")
    other_patient = _path(FIXTURE_KEY, patient_id="MRN0002", study="1.2.4")

    assert first != second
    assert first.parent == second.parent
    assert other_series.parent != first.parent
    assert other_series.parent.parent == first.parent.parent
    assert other_patient.parts[0] != first.parts[0]


@hypothesis.given(any_key, source_patient_ids, source_uids, source_uids, source_uids)
def test_names_are_portable(key, patient_id, study, series, sop):
    path = _path(key, patient_id=patient_id, study=study, series=series, sop=sop)
    text = str(path)

    assert re.fullmatch("DEID-[A-Z2-7]{16}", path.parts[0])
    for part in path.parts[1:3]:
        assert re.fullmatch(r"2\.25\.[1-9][0-9]*", part)
    assert re.fullmatch(r"2\.25\.[1-9][0-9]*\.dcm", path.parts[3])
    assert text.isascii()
    for part in path.parts:
        assert not set(part) & set('<>:"/\\|?*')
        assert all(" " < character < "\x7f" for character in part)
        assert not part.endswith((".", " "))
        assert not part.startswith((".", "-"))
        assert part.split(".")[0].upper() not in RESERVED_DEVICE_NAMES
    assert len(text) <= output_names.MAX_RELATIVE_PATH_LENGTH
    assert text.removesuffix(".dcm") == text.removesuffix(".dcm").upper()
    assert pathlib.PureWindowsPath(text).parts == path.parts


def test_the_longest_path_is_the_documented_bound():
    largest = _uid(uuid.UUID(int=(1 << 128) - 1, version=5).int)

    path = output_names.instance_path(
        patient_id=PSEUDONYM,
        study_instance_uid=largest,
        series_instance_uid=largest,
        sop_instance_uid=largest,
    )

    assert len(largest) == 44
    assert len(str(path)) == output_names.MAX_RELATIVE_PATH_LENGTH == 160


def test_the_same_instance_given_twice_collides():
    instance, other = _path(FIXTURE_KEY), _path(FIXTURE_KEY, sop="1.2.3")

    assert output_names.find_collisions([instance, other, instance]) == ((0, 2),)


def test_one_sop_instance_uid_in_two_series_collides():
    first = _path(FIXTURE_KEY)
    second = _path(FIXTURE_KEY, series=SOURCE["series"] + "0")

    assert first.parent != second.parent
    assert output_names.find_collisions([first, second]) == ((0, 1),)


@hypothesis.given(any_key, st.lists(source_uids, max_size=8, unique=True))
def test_distinct_instances_do_not_collide(key, sops):
    paths = [_path(key, sop=sop) for sop in sops]

    assert not output_names.find_collisions(paths)


def test_collisions_are_ordered_by_first_position_and_hold_only_positions():
    first, second = sorted(
        (_path(FIXTURE_KEY, sop=sop) for sop in ("1.2.3", "1.2.4")),
        key=lambda path: path.name,
        reverse=True,
    )
    single = _path(FIXTURE_KEY, sop="1.2.5")
    paths = [first, second, single, second, first]

    collisions = output_names.find_collisions(iter(paths))

    assert collisions == ((0, 4), (1, 3))
    assert isinstance(collisions, tuple)
    for group in collisions:
        assert isinstance(group, tuple)
        assert all(isinstance(position, int) for position in group)
