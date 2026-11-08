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

"""The review of Parametric Map and Real World Value Mapping for support.

The maintainer added both IODs to the target coverage on 31 October 2026,
with the other IODs that RT exports carry (D-010). Their attributes are
reviewed here against every IOD that the first supported release supported
before them: what they use that no earlier IOD does, and what removal by
Type gives each attribute that has a compound action (D-020, D-022).
"""

import collections
import functools
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    element_rules,
    iods,
    policy,
    run,
    scope,
    temporal_roles,
    uid_roles,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.references import InstanceRecord

from .test_deidentify_pixel_cleaning import Finder
from .test_deidentify_supplementary_actions import (
    MAP_IODS,
    MAP_REVIEWED_AGAINST,
    TEMPORAL_VRS,
    TEXT_VRS,
    _dictionary,
    _resolved_in,
    _record_actions,
    _rules,
    _table_e1_1,
    _used_by,
)

PARAMETRIC_MAP = "Parametric Map"
REAL_WORLD_VALUE_MAPPING = "Real World Value Mapping"
# The attributes that the two IODs use and the IODs reviewed before them do
# not, checked by hand against the 2026d PS3.3 Tables A.75-1, A.46-1,
# C.7.6.24-1, C.7.6.25-1, C.7-22, C.8.32-3, and C.25.2-1 and PS3.6.
NEW_ATTRIBUTES = {
    "(7FE0,0008)": PARAMETRIC_MAP,  # Float Pixel Data
    "(7FE0,0009)": PARAMETRIC_MAP,  # Double Float Pixel Data
    "(0028,0122)": PARAMETRIC_MAP,  # Float Pixel Padding Value
    "(0028,0123)": PARAMETRIC_MAP,  # Double Float Pixel Padding Value
    "(0028,0124)": PARAMETRIC_MAP,  # Float Pixel Padding Range Limit
    "(0028,0125)": PARAMETRIC_MAP,  # Double Float Pixel Padding Range Limit
    "(0028,1230)": PARAMETRIC_MAP,  # Stored Value Color Range Sequence
    "(0028,1231)": PARAMETRIC_MAP,  # Minimum Stored Value Mapped
    "(0028,1232)": PARAMETRIC_MAP,  # Maximum Stored Value Mapped
    "(0040,9092)": PARAMETRIC_MAP,  # Parametric Map Frame Type Sequence
    # Referenced Image Real World Value Mapping Sequence
    "(0040,9094)": REAL_WORLD_VALUE_MAPPING,
}
NEW_VRS = {"OF": 1, "OD": 1, "FL": 2, "FD": 4, "SQ": 3}


def test_both_iods_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(MAP_IODS) <= set(tables.iods)
    assert set(MAP_IODS) <= scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_they_use_no_text_uid_name_url_or_date_that_earlier_iods_do_not():
    for vrs in (TEXT_VRS, TEMPORAL_VRS, {"UI"}, {"PN"}, {"UR"}):
        assert not _used_by(MAP_IODS, vrs) - _used_by(MAP_REVIEWED_AGAINST, vrs), vrs
    # So each already has its rule or its role.
    rules = _rules()
    listed = set(_table_e1_1())
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    for tag in _used_by(MAP_IODS, TEXT_VRS) - listed:
        assert rules[tag].note.strip(), tag
    for tag in _used_by(MAP_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(MAP_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag


def test_their_new_attributes_are_pixel_data_padding_colour_ranges_and_mappings():
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = _used_by(MAP_IODS, every_vr) - _used_by(MAP_REVIEWED_AGAINST, every_vr)

    assert new == set(NEW_ATTRIBUTES)
    for tag, name in NEW_ATTRIBUTES.items():
        assert tag in _used_by((name,), every_vr), tag
    assert all(len(dictionary[tag].vrs) == 1 for tag in new)
    by_vr = collections.Counter(dictionary[tag].vrs[0] for tag in new)
    assert by_vr == NEW_VRS


def test_their_new_attributes_are_kept_by_the_default_where_defined():
    # None is listed in Table E.1-1, given a rule, or a UID, so each takes
    # the default, which keeps it where its IOD defines it, under every
    # preset, with a sequence's items handled by their own rules.
    tables = iods.load_iod_tables()
    listed = set(_table_e1_1())
    uids = set(uid_roles.load_uid_roles().rules)
    assert not set(NEW_ATTRIBUTES) & (listed | set(_rules()) | uids)
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for name in MAP_IODS:
            iod = tables.iods[name]
            for definition in iod.definitions:
                if definition.tag not in NEW_ATTRIBUTES:
                    continue
                rule = rules_of.rule(definition.tag, definition.path, iod=iod)
                assert (rule.source, rule.action) == (
                    element_rules.RuleSource.DEFAULT,
                    element_rules.KEEP,
                ), (preset, name, definition)


def test_removal_by_type_gives_their_attributes_only_actions_already_reviewed():
    actions_by_tag = _record_actions()
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = {}

    for tag in sorted(_used_by(MAP_IODS, every_vr)):
        action = actions_by_tag.get(tag)
        if action not in compound_actions.COMPOUND_ACTIONS or "x" in tag:
            continue
        resolved = _resolved_in(MAP_IODS, tag, action)
        reviewed = _resolved_in(MAP_REVIEWED_AGAINST, tag, action)
        if not resolved <= reviewed:
            new[tag] = (resolved, reviewed)

    assert not new


def test_no_x_z_falls_on_a_required_attribute_in_either_iod():
    # X/Z on a Type 1 or 1C attribute would write D's dummy value (D-020);
    # neither IOD has such a place.
    table = _table_e1_1()
    tables = iods.load_iod_tables()
    for name in MAP_IODS:
        iod = tables.iods[name]
        for definition in iod.definitions:
            row = table.get(definition.tag)
            if row is None or row.basic_profile != "X/Z":
                continue
            resolved = compound_actions.resolve_in_iod(
                iod, definition.tag, definition.path, "X/Z"
            )
            assert resolved in ("X", "Z"), (name, definition)
            assert compound_actions.strictest_type(
                iod, definition.tag, definition.path
            ) not in ("1", "1C"), (name, definition)


KEY = DeidKey(bytes(range(32)))
# Apparent diffusion coefficients in square micrometres per second, as a
# Parametric Map written as 32-bit floats holds them.
FLOAT_VALUES = np.array([0.0, 812.5, 1625.25, 2437.75, 0.0, 903.5, 1807.0, 2710.5])


@functools.lru_cache(maxsize=None)
def _corpus_file(name: str) -> bytes:
    (found,) = (
        file.data for file in corpus_module.build_corpus().files if file.name == name
    )
    return found


def _float_parametric_map(double: bool = False) -> bytes:
    """The corpus's Parametric Map with its frames as 32-bit or 64-bit floats,
    in the Floating Point or Double Floating Point Image Pixel Module."""
    dataset = pydicom.dcmread(
        io.BytesIO(_corpus_file(corpus_module.PARAMETRIC_MAP_FILE))
    )
    for keyword in ("PixelData", "BitsStored", "HighBit", "PixelRepresentation"):
        delattr(dataset, keyword)
    if double:
        dataset.BitsAllocated = 64
        dataset.DoubleFloatPixelData = FLOAT_VALUES.astype("<f8").tobytes()
    else:
        dataset.BitsAllocated = 32
        dataset.FloatPixelData = FLOAT_VALUES.astype("<f4").tobytes()
    stream = io.BytesIO()
    pydicom.dcmwrite(stream, dataset, enforce_file_format=True)
    return stream.getvalue()


def _transformed(data: bytes, options, face_review=None, finder=None):
    transform = InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        face_review=face_review,
        finder=finder,
        unvalidated_policy=True,
    )
    return transform(data, InstanceRecord.from_file(data))


FLOAT_KEYWORDS = pytest.mark.parametrize(
    "double, keyword",
    [(False, "FloatPixelData"), (True, "DoubleFloatPixelData")],
    ids=["float", "double"],
)


@pytest.mark.pydicom
@FLOAT_KEYWORDS
def test_a_floating_point_parametric_map_is_written_as_received_without_pixel_options(
    double, keyword
):
    data = _float_parametric_map(double)
    source = pydicom.dcmread(io.BytesIO(data))

    result = _transformed(data, [])

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert getattr(written, keyword) == getattr(source, keyword)
    assert "PixelData" not in written


@pytest.mark.pydicom
@FLOAT_KEYWORDS
def test_clean_pixel_data_sequesters_a_floating_point_parametric_map(double, keyword):
    data = _float_parametric_map(double)
    assert keyword in pydicom.dcmread(io.BytesIO(data))

    finder = Finder()

    result = _transformed(data, [policy.CLEAN_PIXEL_DATA], finder=finder)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNCLEANABLE_PIXEL_DATA,)
    # It is refused before any frame is searched.
    assert not finder.seen


@pytest.mark.pydicom
@FLOAT_KEYWORDS
def test_a_floating_point_parametric_map_needs_a_face_verdict(double, keyword):
    # It can show a face, so Clean Recognizable Visual Features holds it
    # without a verdict, as it holds every image; the QC pack cannot preview
    # it, so no verdict can be given on what it writes.
    data = _float_parametric_map(double)
    assert keyword in pydicom.dcmread(io.BytesIO(data))
    no_verdicts = FaceReview(
        "A-" + "0123456789abcdef" * 2,
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset(),
    )

    result = _transformed(
        data, [policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES], face_review=no_verdicts
    )

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence), result.evidence
