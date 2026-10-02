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

"""The walker's plan of each element's action, made before any value is read.

Every file is synthetic and encoded by hand. Values that must never appear in
a plan carry the text ``SENTINEL``.
"""

import functools
import pickle

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import source, walker
from pymedphys._dicom.deidentify.element_rules import (
    ElementRule,
    ElementRules,
    RuleSource,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.walker import Consumer

from .test_deidentify_file_layout import (
    EXPLICIT,
    IMPLICIT,
    ITEM_END,
    SEQUENCE_END,
    UNDEFINED,
    _explicit,
    _file,
    _implicit,
    _item,
)

pytestmark = pytest.mark.pydicom

RT_PLAN = b"1.2.840.10008.5.1.4.1.1.481.5\x00"
INSTANCE_UID = b"2.25.7700192\x00"
NAME = b"SENTINEL^NAME "
LABEL = b"SENTINEL PLAN "
BEAM_NAME = b"SENTINEL BEAM "
OTHER_ID = b"SENTINEL ID "
PRIVATE = b"SENTINEL PRIV "
UNLISTED = b"SENTINEL UNKN "
ENCRYPTED = b"SENTINEL ENCR"
SENTINELS = (NAME, LABEL, BEAM_NAME, OTHER_ID, PRIVATE, UNLISTED, ENCRYPTED)

COLLECTION = frozenset({Consumer.RESIDUAL_COLLECTION})


def _path(*steps):
    return ElementPath(tuple(steps[:-1]), steps[-1])


@functools.lru_cache(maxsize=None)
def _rt_plan():
    return load_iod_tables().iods["RT Plan"]


@functools.lru_cache(maxsize=None)
def _rules(preset="basic"):
    return ElementRules(compose_policy(preset))


def _rt_plan_data_set():
    """An RT Plan with kept, emptied, replaced, and removed elements.

    Other Patient IDs Sequence (0010,1002) holds a nested sequence, and Beam
    Sequence (300A,00B0) has undefined lengths.
    """
    return (
        _explicit(0x00080005, "CS", b"ISO_IR 100")
        + _explicit(0x00080016, "UI", RT_PLAN)
        + _explicit(0x00080018, "UI", INSTANCE_UID)
        + _explicit(0x00089999, "LO", UNLISTED)
        + _explicit(0x00091001, "LO", PRIVATE)
        + _explicit(0x00100010, "PN", NAME)
        + _explicit(
            0x00101002,
            "SQ",
            _item(
                _explicit(0x00100020, "LO", OTHER_ID)
                + _explicit(
                    0x00101002, "SQ", _item(_explicit(0x00100020, "LO", OTHER_ID))
                )
            ),
        )
        + _explicit(0x00280010, "US", b"\x00\x02")
        + _explicit(
            0x04000500, "SQ", _item(_explicit(0x04000520, "OB", ENCRYPTED + b"\x00"))
        )
        + _explicit(0x300A0002, "SH", LABEL)
        + _explicit(0x300A00B0, "SQ", length=UNDEFINED)
        + _item(length=UNDEFINED)
        + _explicit(0x300A00C0, "IS", b"1 ")
        + _explicit(0x300A00C2, "LO", BEAM_NAME)
        + ITEM_END
        + _item(_explicit(0x300A00C0, "IS", b"2 "))
        + SEQUENCE_END
        + _explicit(0xFFFCFFFC, "OB", bytes(4))
    )


def _plan(data_set=None, rules=None, transfer_syntax=EXPLICIT):
    data_set = _rt_plan_data_set() if data_set is None else data_set
    evidence = source.read_source(_file(transfer_syntax, data_set))
    return walker.plan_instance(evidence, rules or _rules(), _rt_plan())


def _by_path(plan):
    return {element.path: element for element in plan.elements}


OTHER_IDS = _path("(0010,1002)")
NESTED_OTHER_IDS = _path(("(0010,1002)", 0), "(0010,1002)")
ENCRYPTED_ATTRIBUTES = _path("(0400,0500)")
BEAM_SEQUENCE = _path("(300A,00B0)")

# The action and consumers of each element of the RT Plan under the Basic
# Profile, in file order: (path, action, consumers, removed with).
EXPECTED = [
    (_path("(0008,0005)"), "K", set(), None),
    (_path("(0008,0016)"), "U", {Consumer.UID_REPLACEMENT}, None),
    (_path("(0008,0018)"), "U", {Consumer.UID_REPLACEMENT}, None),
    (_path("(0008,9999)"), "X", set(), None),
    (_path("(0009,1001)"), "X", set(), None),
    (_path("(0010,0010)"), "Z", set(), None),
    (OTHER_IDS, "X", set(), None),
    (_path(("(0010,1002)", 0), "(0010,0020)"), "X", set(), OTHER_IDS),
    (NESTED_OTHER_IDS, "X", set(), OTHER_IDS),
    (
        _path(("(0010,1002)", 0), ("(0010,1002)", 0), "(0010,0020)"),
        "X",
        set(),
        OTHER_IDS,
    ),
    (_path("(0028,0010)"), "K", set(), None),
    (ENCRYPTED_ATTRIBUTES, "X", set(), None),
    (_path(("(0400,0500)", 0), "(0400,0520)"), "X", set(), ENCRYPTED_ATTRIBUTES),
    (_path("(300A,0002)"), "D", {Consumer.DUMMY_COMPARISON}, None),
    (BEAM_SEQUENCE, "K", set(), None),
    (_path(("(300A,00B0)", 0), "(300A,00C0)"), "K", set(), None),
    (_path(("(300A,00B0)", 0), "(300A,00C2)"), "X", set(), None),
    (_path(("(300A,00B0)", 1), "(300A,00C0)"), "K", set(), None),
    (_path("(FFFC,FFFC)"), "X", set(), None),
]
# Sequences hold no value of their own to collect; every other element whose
# value is removed or replaced is collected.
SEQUENCES = {OTHER_IDS, NESTED_OTHER_IDS, ENCRYPTED_ATTRIBUTES, BEAM_SEQUENCE}


def test_each_element_is_planned_in_file_order_with_its_action_and_consumers():
    plan = _plan()

    found = [
        (each.path, each.action, set(each.consumers), each.removed_with)
        for each in plan.elements
    ]
    expected = [
        (
            path,
            action,
            consumers | (set() if action == "K" or path in SEQUENCES else COLLECTION),
            removed_with,
        )
        for path, action, consumers, removed_with in EXPECTED
    ]

    assert found == expected
    assert not plan.sequestrations


def test_the_rule_is_the_rule_of_every_element_and_compound_actions_are_resolved():
    elements = _by_path(_plan())

    beam_name = elements[_path(("(300A,00B0)", 0), "(300A,00C2)")]
    assert beam_name.rule == ElementRule(
        "(300A,00C2)", RuleSource.SUPPLEMENTARY, "X/Z/D", "(300A,00C2)"
    )
    # Beam Name is Type 3 in Beam Sequence, so X/Z/D resolves to X.
    assert beam_name.action == "X"

    assert elements[_path("(0009,1001)")].rule.source is RuleSource.PRIVATE
    assert elements[_path("(0008,9999)")].rule.source is RuleSource.NOT_IN_DICTIONARY
    assert elements[ENCRYPTED_ATTRIBUTES].rule.source is RuleSource.ENGINE
    assert elements[_path("(FFFC,FFFC)")].rule.source is RuleSource.ENGINE


def test_the_descendants_of_a_removed_sequence_take_no_rule_but_are_collected():
    # Patient ID within Other Patient IDs Sequence is Type 1 there, so its
    # own rule, Z/D, would resolve to D; the sequence's removal decides.
    elements = _by_path(_plan())

    for path in (
        _path(("(0010,1002)", 0), "(0010,0020)"),
        _path(("(0010,1002)", 0), ("(0010,1002)", 0), "(0010,0020)"),
        _path(("(0400,0500)", 0), "(0400,0520)"),
    ):
        assert elements[path].rule is None
        assert elements[path].action == "X"
        assert elements[path].consumers == COLLECTION
    assert elements[NESTED_OTHER_IDS].removed_with == OTHER_IDS
    assert elements[NESTED_OTHER_IDS].consumers == frozenset()


def test_the_vr_is_as_written_or_from_the_dictionary_and_unknown_otherwise():
    explicit = _by_path(_plan())
    implicit = _by_path(
        _plan(
            _implicit(0x00091001, PRIVATE)
            + _implicit(0x00100010, NAME)
            + _implicit(0x300A00B0, _item(_implicit(0x300A00C2, BEAM_NAME))),
            transfer_syntax=IMPLICIT,
        )
    )

    assert explicit[_path("(0009,1001)")].vr == "LO"
    assert explicit[_path("(0010,0010)")].vr == "PN"
    assert implicit[_path("(0010,0010)")].vr == "PN"
    assert implicit[_path(("(300A,00B0)", 0), "(300A,00C2)")].vr == "LO"
    # A private element in implicit VR has no VR to read it by; it is still
    # collected, for the collection to say whether it can be.
    assert implicit[_path("(0009,1001)")].vr is None
    assert implicit[_path("(0009,1001)")].consumers == COLLECTION


def test_cleaning_is_a_consumer_under_clean_descriptors():
    elements = _by_path(_plan(rules=_rules("basic-clean-descriptors")))

    beam_name = elements[_path(("(300A,00B0)", 0), "(300A,00C2)")]
    assert beam_name.action == "C"
    assert beam_name.consumers == {Consumer.CLEANING, Consumer.RESIDUAL_COLLECTION}


class _Overridden(ElementRules):
    """The Basic Profile's rules, with some actions replaced by tag."""

    def __init__(self, actions, source=None):
        super().__init__(compose_policy("basic"))
        self._actions = actions
        self._source = source

    def rule(self, tag, path=(), *, iod=None):
        found = super().rule(tag, path, iod=iod)
        action = self._actions.get(tag)
        return (
            found
            if action is None
            else ElementRule(tag, self._source or found.source, action, found.entry)
        )


def test_a_sequence_is_descended_under_k_or_u_and_removed_under_any_other_action():
    data_set = _explicit(0x300A00B0, "SQ", _item(_explicit(0x300A00C0, "IS", b"1 ")))
    beam_number = _path(("(300A,00B0)", 0), "(300A,00C0)")

    for action, removed in [
        ("K", False),
        ("U", False),
        ("Z", True),
        ("D", True),
        ("X", True),
    ]:
        elements = _by_path(_plan(data_set, _Overridden({"(300A,00B0)": action})))

        assert elements[BEAM_SEQUENCE].rule.action == action
        assert elements[BEAM_SEQUENCE].consumers == frozenset()
        if removed:
            assert elements[beam_number].removed_with == BEAM_SEQUENCE
            assert elements[beam_number].rule is None
        else:
            assert elements[beam_number].removed_with is None
            assert elements[beam_number].action == "K"


def test_x_z_on_a_type_1_attribute_gives_d():
    # RT Plan Label (300A,0002) is Type 1 in an RT Plan, so the Z that X/Z
    # offers writes D's dummy value, as decided on 1 October 2026.
    plan = _plan(rules=_Overridden({"(300A,0002)": "X/Z"}))
    label = _by_path(plan)[_path("(300A,0002)")]

    assert label.rule.action == "X/Z"
    assert label.action == "D"
    assert label.consumers == {
        Consumer.DUMMY_COMPARISON,
        Consumer.RESIDUAL_COLLECTION,
    }
    assert not plan.sequestrations


def test_d_where_the_vr_has_no_dummy_value_sequesters_the_instance():
    plan = _plan(rules=_Overridden({"(300A,00B0)": "D", "(0008,0005)": "D"}))
    elements = _by_path(plan)

    assert plan.sequestrations == (
        walker.Sequestration(
            _path("(0008,0005)"), "D", "CS", walker.SequesterReason.NO_DUMMY_VALUE
        ),
        walker.Sequestration(
            BEAM_SEQUENCE, "D", "SQ", walker.SequesterReason.NO_DUMMY_VALUE
        ),
    )
    assert str(plan.sequestrations[1]) == (
        "D on (300A,00B0) needs a dummy value, which VR SQ does not have and "
        "no reviewed rule gives, so the instance must be sequestered"
    )
    # The sequence's items go with it, and every other element is still
    # planned, so that every reason is known.
    assert elements[_path(("(300A,00B0)", 1), "(300A,00C0)")].removed_with == (
        BEAM_SEQUENCE
    )
    assert len(plan.elements) == len(EXPECTED)


def test_a_plain_d_where_the_iod_does_not_define_the_attribute_removes_it():
    # Note 13 after Table E.1-1a: Verifying Observer Sequence (0040,A073) is
    # D, but an RT Plan does not define it, so it is removed (D-020).
    plan = _plan(_explicit(0x0040A073, "SQ", _item(_explicit(0x0040A075, "PN", NAME))))
    observer, name = plan.elements

    assert observer.rule.action == "D"
    assert (observer.action, observer.consumers) == ("X", frozenset())
    assert name.removed_with == observer.path
    assert name.consumers == COLLECTION
    assert not plan.sequestrations


def test_person_identification_code_sequence_has_a_reviewed_dummy_value():
    # D-021: D on Person Identification Code Sequence (0040,1101) writes one
    # item of constants, which must differ from each source item's Code
    # Value and Code Meaning. RT Assertions Sequence (0044,0110) and
    # Asserter Identification Sequence (0044,0103) are kept.
    code = _explicit(0x00080100, "SH", b"SENTINEL")
    code += _explicit(0x00080102, "SH", b"99LOCAL ")
    code += _explicit(0x00080104, "LO", NAME)
    plan = _plan(
        _explicit(
            0x00440110,
            "SQ",
            _item(
                _explicit(
                    0x00440103,
                    "SQ",
                    _item(_explicit(0x00401101, "SQ", _item(code))),
                )
            ),
        )
    )
    elements = _by_path(plan)
    codes = _path(("(0044,0110)", 0), ("(0044,0103)", 0), "(0040,1101)")

    def item(tag):
        return elements[ElementPath((*codes.items, (codes.tag, 0)), tag)]

    assert not plan.sequestrations
    assert elements[codes].action == "D"
    assert item("(0008,0100)").consumers == COLLECTION | {Consumer.DUMMY_COMPARISON}
    assert item("(0008,0104)").consumers == COLLECTION | {Consumer.DUMMY_COMPARISON}
    assert item("(0008,0102)").consumers == COLLECTION
    assert item("(0008,0100)").removed_with == codes


def test_a_plain_z_on_a_type_1_attribute_writes_and_compares_a_dummy_value():
    elements = _by_path(_plan(rules=_Overridden({"(300A,0002)": "Z"})))

    assert elements[_path("(300A,0002)")].rule.action == "Z"
    assert elements[_path("(300A,0002)")].action == "D"
    assert elements[_path("(300A,0002)")].consumers == (
        COLLECTION | {Consumer.DUMMY_COMPARISON}
    )
    # Patient's Name is Type 2, so Z empties it.
    assert elements[_path("(0010,0010)")].consumers == COLLECTION


PATIENT_SETUPS = _path("(300A,0180)")
PREPARATIONS = _path(("(300A,0180)", 0), "(300A,079F)")
PHOTOS = _path(("(300A,0180)", 0), ("(300A,079F)", 0), "(300A,078C)")
PHOTO_ITEM = (*PHOTOS.items, (PHOTOS.tag, 0))


def _patient_setup_photo():
    """A Patient Setup Sequence whose photo has a description.

    Patient Setup Photo Description (300A,0794), which Table E.1-1 gives X,
    is Type 2 in Referenced Patient Setup Photo Sequence (300A,078C), which
    is Type 3 in Patient Treatment Preparation Sequence (300A,079F), itself
    Type 3 in Patient Setup Sequence (300A,0180) of an RT Plan.
    """
    photo = _explicit(0x00081155, "UI", INSTANCE_UID)
    photo += _explicit(0x300A0794, "LT", LABEL)
    preparation = _explicit(0x300A078C, "SQ", _item(photo))
    setup = _explicit(0x300A0182, "IS", b"1 ")
    setup += _explicit(0x300A079F, "SQ", _item(preparation))
    return _explicit(0x300A0180, "SQ", _item(setup))


def test_a_plain_x_where_the_iod_requires_the_attribute_removes_a_type_3_sequence():
    # D-020: the attribute is removed, and with it the innermost enclosing
    # sequence that is Type 3 at its own place, with everything in it, the
    # elements before the attribute included.
    plan = _plan(_patient_setup_photo())
    elements = _by_path(plan)
    description = ElementPath(PHOTO_ITEM, "(300A,0794)")

    assert not plan.sequestrations
    assert (elements[PATIENT_SETUPS].action, elements[PREPARATIONS].action) == (
        "K",
        "K",
    )
    photos = elements[PHOTOS]
    assert photos.rule.action == "K"
    assert (photos.action, photos.removed_with) == ("X", None)
    assert photos.removed_for == description
    assert photos.consumers == frozenset()
    for path in (ElementPath(PHOTO_ITEM, "(0008,1155)"), description):
        assert elements[path].rule is None
        assert (elements[path].action, elements[path].removed_with) == ("X", PHOTOS)
        assert elements[path].removed_for is None
        assert elements[path].consumers == COLLECTION
    assert elements[_path(("(300A,0180)", 0), "(300A,0182)")].action == "K"


def test_a_plain_x_where_the_iod_requires_the_attribute_and_no_sequence_sequesters():
    # Responsible Person (0010,2297) is Type 2C in the Patient Module, and no
    # sequence encloses it (D-020).
    plan = _plan(_explicit(0x00100010, "PN", NAME) + _explicit(0x00102297, "PN", NAME))
    name, person = plan.elements

    assert (person.action, person.removed_for) == ("X", None)
    assert plan.sequestrations == (
        walker.Sequestration(
            person.path, "X", "PN", walker.SequesterReason.REQUIRED_BY_IOD
        ),
    )
    assert str(plan.sequestrations[0]) == (
        "X on (0010,2297) removes an attribute that the IOD requires there, "
        "and no enclosing sequence that the IOD makes Type 3 can be removed "
        "with it, so the instance must be sequestered"
    )
    assert name.action == "Z"


def test_removing_overlay_data_removes_every_attribute_of_its_group():
    # The CT Image IOD includes the Overlay Plane Module as user-optional, so
    # removing Overlay Data (6000,3000) removes its group, but not another
    # overlay's (D-020).
    data_set = (
        _explicit(0x60000010, "US", b"\x00\x02")
        + _explicit(0x60003000, "OW", bytes(4))
        + _explicit(0x60004000, "LT", LABEL)
        + _explicit(0x60020010, "US", b"\x00\x02")
    )
    evidence = source.read_source(_file(EXPLICIT, data_set))
    ct = load_iod_tables().iods["CT Image"]
    plan = walker.plan_instance(evidence, _rules(), ct)
    rows, data, comments, other = plan.elements

    assert not plan.sequestrations
    assert rows.rule.action == "K"
    assert (rows.action, rows.removed_for) == ("X", data.path)
    assert rows.consumers == COLLECTION
    assert (data.action, data.removed_for) == ("X", None)
    # Overlay Comments is removed by its own rule.
    assert (comments.action, comments.removed_for) == ("X", None)
    assert (other.action, other.removed_for) == ("K", None)


def test_the_engine_removes_its_attributes_alone_whatever_their_type():
    # Encrypted Attributes Sequence (0400,0500) is Type 1C in the SOP Common
    # Module; the engine removes it alone, as its condition never holds in
    # the output. A plain X from another rule would sequester.
    data_set = _explicit(0x00102297, "PN", NAME)
    engine = _plan(data_set, _Overridden({"(0010,2297)": "X"}, RuleSource.ENGINE))
    table = _plan(data_set, _Overridden({"(0010,2297)": "X"}))

    assert not engine.sequestrations
    assert engine.elements[0].action == "X"
    assert table.sequestrations
    assert _by_path(_plan())[ENCRYPTED_ATTRIBUTES].removed_for is None


def test_a_value_in_a_form_that_the_dictionary_does_not_allow_sequesters():
    # Rows (0028,0010) written as LO, and Beam Sequence (300A,00B0) written
    # as OB, whose bytes are kept opaque rather than read as items, would
    # each be kept, by the rule for attributes that no rule covers, in a form
    # that is not the attribute's.
    plan = _plan(
        _explicit(0x00280010, "LO", NAME)
        + _explicit(0x300A00B0, "OB", _item(_explicit(0x00100010, "PN", NAME)))
    )
    rows, beams = plan.elements

    assert (rows.action, beams.action) == ("K", "K")
    assert plan.sequestrations == (
        walker.Sequestration(
            rows.path, "K", "LO", walker.SequesterReason.VR_NOT_IN_DICTIONARY
        ),
        walker.Sequestration(
            beams.path, "K", "OB", walker.SequesterReason.VR_NOT_IN_DICTIONARY
        ),
    )
    assert str(plan.sequestrations[0]) == (
        "(0028,0010) is written with VR LO, which the pinned data dictionary "
        "does not give it, so the instance must be sequestered"
    )


def test_admission_refuses_a_sequence_whose_value_is_not_items():
    # The plan relies on admission for this, so it needs no reason of its
    # own: the value of an attribute that the dictionary makes a sequence,
    # written as UN or in implicit VR, must read as items.
    for transfer_syntax, element in [
        (EXPLICIT, _explicit(0x300A00B0, "UN", b"SENTINEL")),
        (IMPLICIT, _implicit(0x300A00B0, b"SENTINEL")),
    ]:
        with pytest.raises(source.SourceRefused):
            _plan(element, transfer_syntax=transfer_syntax)


def test_a_removed_element_in_a_form_the_dictionary_does_not_allow_is_removed():
    # Study Description (0008,1030), which is removed, written as US.
    plan = _plan(_explicit(0x00081030, "US", b"\x00\x02"))

    assert plan.elements[0].action == "X"
    assert not plan.sequestrations


def test_sequences_written_as_un_empty_or_removed_inside_a_kept_item():
    # Beam Sequence as UN in an explicit VR file, with implicit VR items
    # (PS3.5 Section 6.2.2); an empty sequence; and, in a kept item, a
    # removed sequence and Data Set Trailing Padding.
    beam = _implicit(0x00101002, _item(_implicit(0x00100020, OTHER_ID)))
    beam += _implicit(0xFFFCFFFC, bytes(4))
    plan = _plan(
        _explicit(0x00101002, "SQ")
        + _explicit(0x300A00B0, "UN", _item(beam), length=UNDEFINED)
        + SEQUENCE_END
    )
    elements = _by_path(plan)
    removed = _path(("(300A,00B0)", 0), "(0010,1002)")

    assert elements[OTHER_IDS].action == "X"
    assert elements[OTHER_IDS].consumers == frozenset()
    assert elements[BEAM_SEQUENCE].vr == "SQ"
    assert elements[BEAM_SEQUENCE].action == "K"
    assert elements[removed].action == "X"
    assert elements[removed].removed_with is None
    nested = _path(("(300A,00B0)", 0), ("(0010,1002)", 0), "(0010,0020)")
    assert elements[nested].removed_with == removed
    padding = elements[_path(("(300A,00B0)", 0), "(FFFC,FFFC)")]
    assert (padding.action, padding.consumers) == ("X", COLLECTION)
    assert not plan.sequestrations


def test_nothing_is_decoded(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the plan read a value")

    monkeypatch.setattr(source.SourceEvidence, "dataset", refuse)
    monkeypatch.setattr(source.SourceEvidence, "value_field", refuse)

    assert len(_plan().elements) == len(EXPECTED)


def test_the_plan_needs_decoding_only_for_its_consumers():
    plan = _plan()

    assert plan.to_decode() == tuple(
        each.path for each in plan.elements if each.consumers
    )
    assert _path("(0010,0010)") in plan.to_decode()
    assert _path("(0028,0010)") not in plan.to_decode()
    assert BEAM_SEQUENCE not in plan.to_decode()


def test_the_plan_holds_no_value():
    plan = _plan(rules=_Overridden({"(300A,00B0)": "D"}))
    shown = (
        repr(plan)
        + str(plan.sequestrations[0])
        + repr(pickle.loads(pickle.dumps(plan)))
    )

    for sentinel in SENTINELS:
        assert sentinel.decode().strip() not in shown
    assert "SENTINEL" not in shown
