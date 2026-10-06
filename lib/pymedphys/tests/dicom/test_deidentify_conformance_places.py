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

"""The places where the conformance statement resolves an action by Type.

Every instance that the walker plans here is synthetic and encoded by hand.
"""

import re

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    conformance,
    conformance_markdown,
    element_rules,
    iods,
    policy,
    scope,
    source,
    walker,
)

from .test_deidentify_conformance import (
    _entry,
    _removed_with_a_sequence,
    _section,
    _sequence_action,
    _statement,
)
from .test_deidentify_file_layout import EXPLICIT, _explicit, _file, _item

# Series Description, X in the Basic Profile, is Type 1 in Source Series
# Information Sequence, which is Type 3 in the RT Structure Set IOD.
SERIES_DESCRIPTION = "(0008,103E)"
SOURCE_SERIES_INFORMATION = ("(3006,004C)",)
RESPONSIBLE_PERSON = "(0010,2297)"  # X; Type 2C at the top level
OVERLAY_DATA = "(60xx,3000)"  # X; its Overlay Plane Module is U in CT Image
VERIFYING_OBSERVER_SEQUENCE = "(0040,A073)"  # D; only Structured Report IODs
# Attribute Modification DateTime, D, within Original Attributes Sequence,
# which the Basic Profile gives X.
ATTRIBUTE_MODIFICATION_DATETIME = "(0400,0562)"
ORIGINAL_ATTRIBUTES = "(0400,0561)"
ROI_INTERPRETER_SEQUENCE = "(3006,004E)"  # X in the Basic Profile
SOP_CLASS_UID = "(0008,0016)"  # Type 1 at the top level of CT Image


@pytest.fixture(name="preset", scope="module", params=list(policy.PRESETS))
def _preset(request):
    return request.param


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_plain_actions_are_resolved_by_type_at_every_place(preset):
    statement = _statement(preset)
    sequence_action = _sequence_action(policy.compose_policy(preset))
    tables = iods.load_iod_tables()
    extents = compound_actions.RemovalExtent
    for entry in statement.attributes:
        if entry.action in compound_actions.COMPOUND_ACTIONS:
            continue
        tag = entry.tag.replace("60xx", "6000")
        if entry.action not in ("X", "Z", "D") or not re.fullmatch(
            r"\([0-9A-F]{4},[0-9A-F]{4}\)", tag
        ):
            assert (entry.places, entry.elsewhere) == ((), ""), entry.tag
            continue
        assert entry.elsewhere == {"X": "X", "Z": "Z", "D": "X"}[entry.action]
        expected = []
        for name in sorted(scope.SUPPORTED_IODS):
            iod = tables.iods[name]
            paths = dict.fromkeys(d.path for d in iod.definitions if d.tag == entry.tag)
            for path in paths:
                if _removed_with_a_sequence(sequence_action, iod, path):
                    continue
                if entry.action != "X":
                    action = compound_actions.resolve_plain_in_iod(
                        iod, tag, path, entry.action
                    )
                    expected.append(conformance.Place(name, path, action))
                    continue
                removal = compound_actions.resolve_plain_x_in_iod(iod, tag, path)
                place = {
                    extents.ATTRIBUTE: conformance.Place(name, path, "X"),
                    extents.SEQUESTER: conformance.Place(
                        name, path, conformance.SEQUESTER
                    ),
                    extents.OVERLAY_GROUP: conformance.Place(
                        name, path, "X", conformance.OVERLAY_GROUP
                    ),
                }.get(removal.extent)
                if removal.extent is extents.SEQUENCE:
                    place = conformance.Place(name, path, "X", path[removal.sequence])
                expected.append(place)
        assert entry.places == tuple(expected), entry.tag


def _row(text, tag):
    return next(line for line in text.splitlines() if f"| {tag} |" in line)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_plain_x_on_a_required_attribute_removes_its_sequence():
    statement = _statement("basic")
    place = conformance.Place(
        "RT Structure Set", SOURCE_SERIES_INFORMATION, "X", SOURCE_SERIES_INFORMATION[0]
    )
    assert place in _entry(statement, SERIES_DESCRIPTION).places
    row = _row(conformance_markdown.render_markdown(statement), SERIES_DESCRIPTION)
    # The enclosing sequence that is removed is not named again as the place.
    assert (
        "| X with the enclosing Source Series Information Sequence (3006,004C) "
        "in RT Structure Set. X elsewhere. |" in row
    )
    # Where the removed sequence is the place's own, only the sequences
    # outside it are named as the place.
    row = _row(conformance_markdown.render_markdown(statement), "(300A,0794)")
    assert (
        "| X with the enclosing Referenced Patient Setup Photo Sequence "
        "(300A,078C) within Patient Treatment Preparation Sequence (300A,079F) "
        "in CT Image;" in row
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_plain_x_that_no_removal_keeps_valid_sequesters():
    statement = _statement("basic")
    assert conformance.Place("CT Image", (), conformance.SEQUESTER) in (
        _entry(statement, RESPONSIBLE_PERSON).places
    )
    row = _row(conformance_markdown.render_markdown(statement), RESPONSIBLE_PERSON)
    assert "instance sequestered at the top level" in row


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_plain_x_on_overlay_data_removes_its_overlay_group():
    statement = _statement("basic")
    assert conformance.Place("CT Image", (), "X", conformance.OVERLAY_GROUP) in (
        _entry(statement, OVERLAY_DATA).places
    )
    row = _row(conformance_markdown.render_markdown(statement), OVERLAY_DATA)
    assert "X with its overlay group at the top level in CT Image" in row


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_plain_d_that_no_supported_iod_defines_is_removed():
    entry = _entry(_statement("basic"), VERIFYING_OBSERVER_SEQUENCE)
    assert (entry.action, entry.places, entry.elsewhere) == ("D", (), "X")
    row = _row(
        conformance_markdown.render_markdown(_statement("basic")),
        VERIFYING_OBSERVER_SEQUENCE,
    )
    assert row.endswith("| X elsewhere. |")


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_plain_z_on_a_type_1_attribute_gives_d(preset):
    # No supported IOD has a Type 1 place for an attribute given plain Z, so
    # the D branch is exercised directly at a Type 1 place.
    ct_image = iods.load_iod_tables().iods["CT Image"]
    assert compound_actions.strictest_type(ct_image, SOP_CLASS_UID, ()) == "1"
    # pylint: disable-next=protected-access
    place = conformance._place(ct_image, "CT Image", SOP_CLASS_UID, (), "Z")
    assert place == conformance.Place("CT Image", (), "D")

    statement = _statement(preset)
    tables = iods.load_iod_tables()
    zeroed = [e for e in statement.attributes if e.action == "Z" and e.places]
    assert zeroed
    for entry in zeroed:
        for place in entry.places:
            iod = tables.iods[place.iod]
            required = compound_actions.strictest_type(iod, entry.tag, place.path) in (
                "1",
                "1C",
            )
            assert place.action == ("D" if required else "Z"), entry.tag


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_plain_actions_by_type_are_no_longer_pending(preset):
    assert not any("D-020" in item for item in conformance.PENDING)
    pending = _statement(preset).pending
    assert not any("D-020" in item for item in pending)
    section = _section(
        conformance_markdown.render_markdown(_statement(preset)), "Actions"
    )
    assert "Note 13 after Table E.1-1a" in section
    assert "innermost enclosing sequence" in section
    # The walker plans the removals that D-020 decides for a plain X.
    assert "not yet apply" not in " ".join(section.split())


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_last_column_lists_places_that_remove_more_than_the_attribute():
    section = _section(
        conformance_markdown.render_markdown(_statement("basic")), "Actions"
    )
    assert (
        "the action differs from that elsewhere or removes more than the "
        "attribute" in " ".join(section.split())
    )


def _plan(iod_name, data_set, preset="basic"):
    """Plan a synthetic data set of an IOD as the walker does."""
    evidence = source.read_source(_file(EXPLICIT, data_set))
    rules = element_rules.ElementRules(policy.compose_policy(preset))
    return walker.plan_instance(evidence, rules, iods.load_iod_tables().iods[iod_name])


def _ct_plan(data_set, preset="basic"):
    """Plan a synthetic CT Image data set as the walker does."""
    return _plan("CT Image", data_set, preset)


def _place(statement, tag, iod_name, path):
    """Return the one place that the statement lists for a tag there."""
    (place,) = (
        place
        for place in _entry(statement, tag).places
        if (place.iod, place.path) == (iod_name, path)
    )
    return place


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.pydicom
def test_the_walker_sequesters_where_the_statement_says():
    # Responsible Person (0010,2297) is Type 2C at the top level of CT Image,
    # and no sequence encloses it, so D-020 sequesters the instance for a
    # plain X on it.
    plan = _ct_plan(_explicit(0x00102297, "PN", b"ZEBEDEE^QUILLON "))
    (element,) = plan.elements
    assert (str(element.path), element.action) == (RESPONSIBLE_PERSON, "X")
    assert plan.sequestrations == (
        walker.Sequestration(
            element.path, "X", "PN", walker.SequesterReason.REQUIRED_BY_IOD
        ),
    )

    statement = _statement("basic")
    place = _place(statement, RESPONSIBLE_PERSON, "CT Image", ())
    assert (place.action, place.removes) == (conformance.SEQUESTER, "")


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.pydicom
def test_the_walker_removes_the_enclosing_sequence_that_the_statement_names():
    # Series Description (0008,103E) is Type 1 within Source Series
    # Information Sequence (3006,004C), which is Type 3 in RT Structure Set,
    # so D-020 removes that sequence with it, and everything in it.
    sequence_tag = SOURCE_SERIES_INFORMATION[0]
    plan = _plan(
        "RT Structure Set",
        _explicit(
            0x3006004C,
            "SQ",
            _item(
                _explicit(0x0008103E, "LO", b"QUILLON SERIES")
                + _explicit(0x0020000E, "UI", b"1.2.826.0.1.3680043.2.1125.1")
            ),
        ),
    )
    sequence, description, series_uid = plan.elements
    assert not plan.sequestrations
    assert str(sequence.path) == sequence_tag
    assert description.path.tag == SERIES_DESCRIPTION
    assert (sequence.action, sequence.removed_for) == ("X", description.path)
    for nested in (description, series_uid):
        assert (nested.action, nested.removed_with) == ("X", sequence.path)

    statement = _statement("basic")
    place = _place(
        statement, SERIES_DESCRIPTION, "RT Structure Set", SOURCE_SERIES_INFORMATION
    )
    assert (place.action, place.removes) == ("X", sequence.path.tag)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.pydicom
def test_the_walker_removes_the_overlay_group_that_the_statement_names():
    # The CT Image IOD includes the Overlay Plane Module as user-optional, so
    # D-020 removes every attribute of the overlay group with Overlay Data
    # (6000,3000), and none of another overlay's.
    plan = _ct_plan(
        _explicit(0x60000010, "US", b"\x00\x02")
        + _explicit(0x60003000, "OW", bytes(4))
        + _explicit(0x60020010, "US", b"\x00\x02")
    )
    rows, data, other = plan.elements
    assert not plan.sequestrations
    assert (data.action, data.removed_for) == ("X", None)
    assert (rows.action, rows.removed_for) == ("X", data.path)
    assert (other.action, other.removed_for) == ("K", None)

    statement = _statement("basic")
    place = _place(statement, OVERLAY_DATA, "CT Image", ())
    assert (place.action, place.removes) == ("X", conformance.OVERLAY_GROUP)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.pydicom
def test_plain_z_and_d_are_resolved_as_the_walker_plans_them():
    # Patient's Name (0010,0010) is Z and Clinical Trial Sponsor Name
    # (0012,0010) D at the top level, and Clinical Trial Protocol ID
    # (0012,0020) D within Consent for Clinical Trial Use Sequence
    # (0012,0083), which the Basic Profile keeps.
    plan = _ct_plan(
        _explicit(0x00100010, "PN", b"ZEBEDEE^QUILLON ")
        + _explicit(0x00120010, "LO", b"SPONSOR7741 ")
        + _explicit(0x00120083, "SQ", _item(_explicit(0x00120020, "LO", b"PROT77")))
    )
    statement = _statement("basic")
    checked = []
    for element in plan.elements:
        if element.rule is None or element.rule.action not in ("Z", "D"):
            continue
        path = tuple(tag for tag, _ in element.path.items)
        places = {
            p.path: p.action
            for p in _entry(statement, element.path.tag).places
            if p.iod == "CT Image"
        }
        assert places[path] == element.action, element.path
        checked.append((element.path.tag, path, element.action))
    assert checked == [
        ("(0010,0010)", (), "Z"),
        ("(0012,0010)", (), "D"),
        ("(0012,0020)", ("(0012,0083)",), "D"),
    ]


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.pydicom
def test_places_within_a_sequence_that_the_policy_removes_are_not_listed():
    # The walker removes Attribute Modification DateTime with Original
    # Attributes Sequence, so the statement lists no place for it there.
    plan = _ct_plan(
        _explicit(
            0x04000561,
            "SQ",
            _item(_explicit(0x04000562, "DT", b"20260102030405")),
        )
    )
    sequence, nested = plan.elements
    assert (str(sequence.path), sequence.action) == (ORIGINAL_ATTRIBUTES, "X")
    assert nested.removed_with == sequence.path

    statement = _statement("basic")
    assert not any(
        ORIGINAL_ATTRIBUTES in place.path
        for entry in statement.attributes
        for place in entry.places
    )
    entry = _entry(statement, ATTRIBUTE_MODIFICATION_DATETIME)
    assert (entry.places, entry.elsewhere) == ((), "X")
    for entry in statement.attributes:
        for place in entry.places:
            assert ROI_INTERPRETER_SEQUENCE not in place.path, entry.tag
    section = " ".join(
        _section(conformance_markdown.render_markdown(statement), "Actions").split()
    )
    assert (
        "A place within a sequence that the engine removes, or replaces, with "
        "everything in it is not listed" in section
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_places_within_a_removed_sequence_follow_the_policy_without_rules():
    # The engine refuses public-release's element rules, so the policy's own
    # actions decide which sequences are removed.
    composed = policy.compose_policy("public-release")
    assert composed.actions[ORIGINAL_ATTRIBUTES] == "X"
    statement = conformance.conformance_statement(composed, vocabulary=None)
    assert not any(
        ORIGINAL_ATTRIBUTES in place.path
        for entry in statement.attributes
        for place in entry.places
    )
