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

"""Compound actions of Table E.1-1a, resolved from the strictest PS3.3 Type."""

import json
import pickle

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import compound_actions, iods, standard

SequesterInstance = compound_actions.SequesterInstance
resolve = compound_actions.resolve
resolve_in_iod = compound_actions.resolve_in_iod
strictest_type = compound_actions.strictest_type

SEQUESTER = "sequester"
# The action each compound action resolves to for each Type, worked by hand
# from the design: the target is D for Type 1, Z for Type 2, and X for Type 3;
# where the compound action does not offer it, the next of X, Z, and D that it
# offers; U in the place of D in X/Z/U*; and sequestration where none follows.
RESOLUTIONS = {
    "X/Z": {"1": SEQUESTER, "1C": SEQUESTER, "2": "Z", "2C": "Z", "3": "X"},
    "X/D": {"1": "D", "1C": "D", "2": "D", "2C": "D", "3": "X"},
    "Z/D": {"1": "D", "1C": "D", "2": "Z", "2C": "Z", "3": "Z"},
    "X/Z/D": {"1": "D", "1C": "D", "2": "Z", "2C": "Z", "3": "X"},
    "X/Z/U*": {"1": "U", "1C": "U", "2": "Z", "2C": "Z", "3": "X"},
}
CASES = [
    (action, attribute_type, expected)
    for action, by_type in RESOLUTIONS.items()
    for attribute_type, expected in by_type.items()
]

FIRST_RELEASE_IODS = ("CT Image", "RT Structure Set", "RT Plan", "RT Dose")
REQUIRED = frozenset({"1", "1C", "2", "2C"})

# A synthetic value standing in for a source attribute value, which no
# message may repeat.
SECRET = "Doe^Jane"

INSTITUTION_NAME = "(0008,0080)"
PATIENT_ID = "(0010,0020)"
REFERENCED_STUDY_SEQUENCE = "(0008,1110)"


@pytest.fixture(name="tables", scope="module")
def _tables():
    return iods.load_iod_tables()


def _row(depth, name, tag, attribute_type):
    return {
        "depth": depth,
        "name": name,
        "tag": tag,
        "type": attribute_type,
        "include": "",
    }


def _synthetic_iod(tmp_path, *definitions, path=()):
    """Return an IOD with one module of each usage, M, C, and U.

    Each definition is ``(usage, type)`` for Institution Name, in the module
    of that usage, within the sequences whose tags ``path`` gives, outermost
    first. A module without a definition holds only Manufacturer (0008,0070).

    The IOD is written as synthetic generated tables and read back with
    :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables`, so it does not
    depend on how the loader builds an IOD.
    """
    types = dict(definitions)
    modules, tables = [], []
    for number, usage in enumerate(("M", "C", "U"), start=1):
        label = f"Table C.0-{number}"
        if usage in types:
            sequences = [
                _row(depth, f"Sequence {depth}", tag, "3")
                for depth, tag in enumerate(path)
            ]
            rows = [
                *sequences,
                _row(len(path), "Institution Name", INSTITUTION_NAME, types[usage]),
            ]
        else:
            rows = [_row(0, "Manufacturer", "(0008,0070)", "3")]
        title = f"Module {usage} Module Attributes"
        tables.append({"label": label, "title": title, "rows": rows})
        modules.append(
            {
                "information_entity": "Equipment",
                "module": f"Module {usage}",
                "section": "C.0",
                "usage": usage,
                "condition": "",
                "table": label,
            }
        )
    iod = {"label": "Table A.0-1", "iod": "Synthetic", "modules": modules}

    paths = []
    for name, rows in (("iod_modules.json", [iod]), ("module_attributes.json", tables)):
        # Keep the generated file's header, with these rows and their digest.
        document = json.loads((standard.STANDARD_DIR / name).read_text("utf-8"))
        document.update(rows=rows, content_sha256=standard.content_sha256(rows))
        paths.append(tmp_path / name)
        paths[-1].write_text(json.dumps(document), encoding="utf-8")
    return iods.load_iod_tables(*paths).iods["Synthetic"]


def test_the_compound_actions_are_those_of_table_e1_1a():
    codes = {row.code for row in standard.load_table_e1_1a().codes}

    assert compound_actions.COMPOUND_ACTIONS == {"X/Z", "X/D", "Z/D", "X/Z/D", "X/Z/U*"}
    assert compound_actions.COMPOUND_ACTIONS == {code for code in codes if "/" in code}
    assert compound_actions.COMPOUND_ACTIONS <= standard.ACTION_CODES


@pytest.mark.parametrize("action, attribute_type, expected", CASES)
def test_each_compound_action_resolves_by_type(action, attribute_type, expected):
    if expected == SEQUESTER:
        with pytest.raises(SequesterInstance):
            resolve(action, attribute_type)
    else:
        assert resolve(action, attribute_type) == expected


@pytest.mark.parametrize(
    "types, expected",
    [
        (("1",), "1"),
        (("1C",), "1"),
        (("2",), "2"),
        (("2C",), "2"),
        (("3",), "3"),
        (("3", "2"), "2"),
        (("3", "2C"), "2"),
        (("2", "1C"), "1"),
        (("2C", "1C"), "1"),
        (("3", "1"), "1"),
    ],
)
def test_the_strictest_type_counts_1c_as_1_and_2c_as_2(tmp_path, types, expected):
    iod = _synthetic_iod(tmp_path, *zip(("M", "C", "U"), types))

    assert strictest_type(iod, INSTITUTION_NAME) == expected


@pytest.mark.parametrize("usage", ["M", "C", "U"])
@pytest.mark.parametrize("attribute_type, expected", [("1C", "D"), ("2C", "Z")])
def test_a_module_of_any_usage_can_give_the_strictest_type(
    tmp_path, usage, attribute_type, expected
):
    # The other two modules make the attribute Type 3, so only the module of
    # this usage can make it required.
    iod = _synthetic_iod(
        tmp_path,
        *((other, "3") for other in ("M", "C", "U") if other != usage),
        (usage, attribute_type),
    )

    assert strictest_type(iod, INSTITUTION_NAME) == attribute_type[0]
    assert resolve_in_iod(iod, INSTITUTION_NAME, (), "X/Z/D") == expected


def test_an_attribute_gets_the_action_of_its_strictest_type_across_modules(tables):
    rt_dose = tables.iods["RT Dose"]
    usage = {module.module: module.usage for module in rt_dose.modules}

    # Content Date and Instance Number are Type 3 in the mandatory RT Dose
    # Module, but Content Date is Type 2C, and Instance Number Type 2, in the
    # General Image Module, which the RT Dose IOD includes conditionally.
    assert {(d.module, d.type) for d in rt_dose.lookup("(0008,0023)")} == {
        ("General Image", "2C"),
        ("RT Dose", "3"),
    }
    assert {(d.module, d.type) for d in rt_dose.lookup("(0020,0013)")} == {
        ("General Image", "2"),
        ("RT Dose", "3"),
        ("SOP Common", "3"),
    }
    assert (usage["General Image"], usage["RT Dose"]) == ("C", "M")

    assert strictest_type(rt_dose, "(0008,0023)") == "2"
    assert resolve_in_iod(rt_dose, "(0008,0023)", (), "Z/D") == "Z"
    assert strictest_type(rt_dose, "(0020,0013)") == "2"
    assert resolve_in_iod(rt_dose, "(0020,0013)", (), "X/Z/D") == "Z"

    # Image Type is Type 3 in the General Image Module and Type 1 in the CT
    # Image Module, both mandatory in the CT Image IOD.
    assert strictest_type(tables.iods["CT Image"], "(0008,0008)") == "1"
    assert resolve_in_iod(tables.iods["CT Image"], "(0008,0008)", (), "X/D") == "D"


@pytest.mark.parametrize(
    "iod, path, expected",
    [
        # Institution Name, X/Z/D in Table E.1-1: Type 3 at the top level of
        # the General Equipment Module, Type 2 in ROI Creator Sequence within
        # Structure Set ROI Sequence, and Type 1C in Referring Physician
        # Identification Sequence.
        ("RT Structure Set", (), "X"),
        ("RT Structure Set", ("(3006,0020)", "(3006,004D)"), "Z"),
        ("RT Structure Set", ("(0008,0096)",), "D"),
        ("CT Image", (), "X"),
        ("CT Image", ("(0008,0096)",), "D"),
    ],
)
def test_the_type_depends_on_the_enclosing_sequence(tables, iod, path, expected):
    assert resolve_in_iod(tables.iods[iod], INSTITUTION_NAME, path, "X/Z/D") == expected


def test_spot_resolutions_in_the_first_release_iods(tables):
    rt_plan = tables.iods["RT Plan"]
    rt_dose = tables.iods["RT Dose"]

    # Patient ID, Z/D: Type 2 at the top level, Type 1 in Other Patient IDs
    # Sequence.
    assert resolve_in_iod(rt_plan, PATIENT_ID, (), "Z/D") == "Z"
    assert resolve_in_iod(rt_plan, PATIENT_ID, ("(0010,1002)",), "Z/D") == "D"
    # RT Plan Date, X/D, is Type 2 in the RT Plan IOD, so it takes D.
    assert strictest_type(rt_plan, "(300A,0006)") == "2"
    assert resolve_in_iod(rt_plan, "(300A,0006)", (), "X/D") == "D"
    # Treatment Machine Name, X/Z, is Type 2 in Beam Sequence.
    assert resolve_in_iod(rt_plan, "(300A,00B2)", ("(300A,00B0)",), "X/Z") == "Z"
    # Referenced Image Sequence, X/Z/U*, is Type 1C in Plan Overview Sequence
    # of the RT Dose IOD, and Type 3 at its top level.
    assert resolve_in_iod(rt_dose, "(0008,1140)", ("(300C,0116)",), "X/Z/U*") == "U"
    assert resolve_in_iod(rt_dose, "(0008,1140)", (), "X/Z/U*") == "X"


@pytest.mark.parametrize(
    "action, expected",
    [("X/Z", "X"), ("X/D", "X"), ("X/Z/D", "X"), ("X/Z/U*", "X"), ("Z/D", "Z")],
)
def test_an_attribute_the_iod_does_not_define_there_is_type_3(tables, action, expected):
    ct = tables.iods["CT Image"]

    # Treatment Machine Name is not part of the CT Image IOD, anywhere, and
    # Patient ID is not defined within Referenced Image Sequence.
    assert ct.lookup("(300A,00B2)") == ()
    assert ct.lookup(PATIENT_ID, ("(0008,1140)",)) == ()

    assert strictest_type(ct, "(300A,00B2)") == "3"
    assert resolve_in_iod(ct, "(300A,00B2)", (), action) == expected
    assert strictest_type(ct, PATIENT_ID, ("(0008,1140)",)) == "3"
    assert resolve_in_iod(ct, PATIENT_ID, ("(0008,1140)",), action) == expected


@pytest.mark.parametrize("attribute_type", ["1", "1C"])
def test_x_z_on_a_type_1_attribute_sequesters_the_instance(tmp_path, attribute_type):
    iod = _synthetic_iod(tmp_path, ("M", "3"), ("C", attribute_type))

    with pytest.raises(SequesterInstance) as raised:
        resolve_in_iod(iod, INSTITUTION_NAME, (), "X/Z")
    error = raised.value

    assert (error.action, error.attribute_type) == ("X/Z", "1")
    assert (error.tag, error.path) == (INSTITUTION_NAME, ())
    assert "sequester" in str(error)

    with pytest.raises(SequesterInstance) as raised:
        resolve("X/Z", attribute_type)
    assert (raised.value.action, raised.value.attribute_type) == (
        "X/Z",
        attribute_type,
    )
    assert (raised.value.tag, raised.value.path) == (None, ())


def test_sequestering_is_not_a_value_error():
    # Code that rejects invalid input by catching ValueError must not also
    # swallow an instance that has to be sequestered.
    assert not issubclass(SequesterInstance, ValueError)
    with pytest.raises(SequesterInstance):
        try:
            resolve("X/Z", "1")
        except ValueError:
            pytest.fail("a ValueError handler caught the sequestration")


def test_the_sequestration_message_names_only_tags_actions_and_the_type(tmp_path):
    path = ("(3006,0020)", "(3006,004D)")
    iod = _synthetic_iod(tmp_path, ("M", "1"), path=path)

    with pytest.raises(SequesterInstance) as raised:
        resolve_in_iod(iod, INSTITUTION_NAME, path, "X/Z")

    assert str(raised.value) == (
        "X/Z on (3006,0020) > (3006,004D) > (0008,0080) offers no action that "
        "Type 1 allows, so the instance must be sequestered"
    )
    assert repr(raised.value) == (
        "SequesterInstance('X/Z', '1', '(0008,0080)', ('(3006,0020)', '(3006,004D)'))"
    )
    # It survives pickling, as between processes.
    copied = pickle.loads(pickle.dumps(raised.value))
    assert (copied.action, copied.tag, copied.path) == ("X/Z", INSTITUTION_NAME, path)
    assert str(copied) == str(raised.value)


def _compound_attributes():
    """Return each (tag, action) to which Table E.1-1 gives a compound action."""
    return {
        (attribute.tag, action)
        for attribute in standard.load_table_e1_1().attributes
        for action in (attribute.basic_profile, *attribute.options.values())
        if action in compound_actions.COMPOUND_ACTIONS
    }


@pytest.fixture(name="resolutions", scope="module")
def _resolutions(tables):
    """Return how each compound action resolves in each generated IOD.

    For each IOD by name, one ``(path, tag, action, types, found)`` for each
    compound action that Table E.1-1 gives an attribute, at each place where
    the IOD defines the attribute: ``types`` are the Types of its definitions
    there, and ``found`` is the resolved action, or the
    :class:`SequesterInstance` raised.
    """
    by_tag = {}
    for tag, action in _compound_attributes():
        by_tag.setdefault(tag, set()).add(action)

    resolutions = {}
    for name, iod in tables.iods.items():
        places = {(d.path, d.tag) for d in iod.definitions if d.tag in by_tag}
        in_iod = []
        for path, tag in sorted(places):
            types = frozenset(d.type for d in iod.lookup(tag, path))
            for action in sorted(by_tag[tag]):
                try:
                    found = resolve_in_iod(iod, tag, path, action)
                except SequesterInstance as error:
                    found = error
                in_iod.append((path, tag, action, types, found))
        resolutions[name] = tuple(in_iod)
    return resolutions


def _check_kept_where_required(where, types, found):
    """Check that a resolved action keeps the attribute where its Type requires it."""
    if types & {"1", "1C"}:
        # Neither removed nor emptied.
        assert found in {"D", "U"}, where
    elif types & REQUIRED:
        assert found != "X", where
    else:
        assert found in {"X", "Z"}, where


def test_no_required_attribute_with_a_compound_action_is_removed(resolutions):
    resolved = set()
    for name in FIRST_RELEASE_IODS:
        for path, tag, action, types, found in resolutions[name]:
            where = (name, path, tag, action)
            # No compound action sequesters an instance of these IODs.
            assert not isinstance(found, SequesterInstance), where
            _check_kept_where_required(where, types, found)
            resolved.add(found)

    # Every outcome occurs, so the sweep is not vacuous.
    assert resolved == {"X", "Z", "D", "U"}


def test_no_required_attribute_with_a_compound_action_is_removed_in_any_generated_iod(
    resolutions,
):
    resolved = set()
    for name, in_iod in resolutions.items():
        for path, tag, action, types, found in in_iod:
            where = (name, path, tag, action)
            if isinstance(found, SequesterInstance):
                # Only X/Z on a Type 1 or 1C attribute sequesters the
                # instance, and the exception says where.
                assert action == "X/Z" and types & {"1", "1C"}, where
                assert (found.action, found.attribute_type) == ("X/Z", "1"), where
                assert (found.tag, found.path) == (tag, path), where
            else:
                _check_kept_where_required(where, types, found)
                resolved.add(found)

    # The sweep covers the first supported release's IODs and the others.
    assert set(FIRST_RELEASE_IODS) < set(resolutions)
    # Every outcome occurs, so the sweep is not vacuous.
    assert resolved == {"X", "Z", "D", "U"}


def test_x_z_sequesters_only_referenced_study_sequence_in_two_generated_iods(
    resolutions,
):
    # Table E.1-1 gives Referenced Study Sequence X/Z under the Basic Profile,
    # and the Related Information Entities Macro (PS3.3 Table 10.37-1) makes
    # it Type 1 within these sequences, so no action that X/Z offers keeps it
    # valid there. A new edition that changes where this happens fails here.
    sequestered = {
        (name, path, tag)
        for name, in_iod in resolutions.items()
        for path, tag, _, _, found in in_iod
        if isinstance(found, SequesterInstance)
    }

    assert sequestered == {
        (
            "RT Patient Position Acquisition Instruction",
            # Acquisition Task Sequence > Acquisition Subtask Sequence >
            # Referenced Position Reference Instance Sequence
            ("(3002,0118)", "(3002,011A)", "(3002,0132)"),
            REFERENCED_STUDY_SEQUENCE,
        ),
        (
            "RT Physician Intent",
            # RT Physician Intent Sequence > RT Physician Intent Input
            # Instance Sequence
            ("(3010,0057)", "(3010,005F)"),
            REFERENCED_STUDY_SEQUENCE,
        ),
        (
            "RT Physician Intent",
            # RT Prescription Sequence > Planning Input Information Sequence
            ("(3010,006B)", "(3010,0076)"),
            REFERENCED_STUDY_SEQUENCE,
        ),
    }


def test_no_attribute_with_x_z_is_type_1_in_the_first_release_iods(tables):
    x_z = {tag for tag, action in _compound_attributes() if action == "X/Z"}
    defined = [
        (name, definition)
        for name in FIRST_RELEASE_IODS
        for definition in tables.iods[name].definitions
        if definition.tag in x_z
    ]

    assert {definition.tag for _, definition in defined} >= {
        "(300A,00B2)",  # Treatment Machine Name
        "(0010,2203)",  # Patient's Sex Neutered
    }
    assert not [
        (name, definition.path, definition.tag)
        for name, definition in defined
        if definition.type in {"1", "1C"}
    ]


@pytest.mark.parametrize("action", ["D", "Z", "X", "K", "C", "U"])
def test_a_plain_action_is_rejected(tables, action):
    with pytest.raises(ValueError, match="not a compound action"):
        resolve(action, "2")
    with pytest.raises(ValueError, match="not a compound action"):
        resolve_in_iod(tables.iods["CT Image"], PATIENT_ID, (), action)


@pytest.mark.parametrize(
    "action", ["X/U", "U*", "x/z", "X/Z/U", "D/Z", "", None, ("X", "Z")]
)
def test_an_unknown_action_is_rejected(action):
    with pytest.raises(ValueError, match="not a compound action"):
        resolve(action, "2")


@pytest.mark.parametrize("attribute_type", ["4", "", "1c", "M", "1C ", None, 1])
def test_an_unknown_type_is_rejected(attribute_type):
    with pytest.raises(ValueError, match="not a Type"):
        resolve("X/Z/D", attribute_type)


@pytest.mark.parametrize(
    "tag",
    [
        "(0010,0020",
        "0010,0020",
        "(0010,002G)",
        # Lower-case digits, which the IOD tables never use, would silently
        # find no definition.
        "(0010,002a)",
        "(60xx,3000)",
        " (0010,0020)",
        "(0010,0020)\n",
        None,
        0x00100020,
    ],
)
def test_a_malformed_tag_is_rejected(tables, tag):
    ct = tables.iods["CT Image"]

    with pytest.raises(ValueError, match="tag"):
        strictest_type(ct, tag)
    with pytest.raises(ValueError, match="tag"):
        resolve_in_iod(ct, tag, (), "X/Z/D")


@pytest.mark.parametrize(
    "path",
    [
        # A single string is not a sequence of tags, even when empty.
        "(0010,1002)",
        "",
        ("(0010,1002",),
        ["(0010,1002)", "(0010,002a)"],
        (None,),
        None,
    ],
)
def test_a_malformed_path_is_rejected(tables, path):
    ct = tables.iods["CT Image"]

    with pytest.raises(ValueError, match="path"):
        strictest_type(ct, PATIENT_ID, path)
    with pytest.raises(ValueError, match="path"):
        resolve_in_iod(ct, PATIENT_ID, path, "Z/D")


def test_a_path_may_be_any_sequence_of_tags(tables):
    ct = tables.iods["CT Image"]

    assert strictest_type(ct, PATIENT_ID, ["(0010,1002)"]) == "1"
    assert resolve_in_iod(ct, PATIENT_ID, ["(0010,1002)"], "Z/D") == "D"


@pytest.mark.parametrize(
    "call",
    [
        lambda iod: resolve(f"X/{SECRET}", "2"),
        lambda iod: resolve("X/Z/D", SECRET),
        lambda iod: strictest_type(iod, SECRET),
        lambda iod: strictest_type(iod, f"({SECRET})"),
        lambda iod: strictest_type(iod, PATIENT_ID, (SECRET,)),
        lambda iod: strictest_type(iod, PATIENT_ID, SECRET),
        lambda iod: resolve_in_iod(iod, SECRET, (), "X/Z/D"),
        lambda iod: resolve_in_iod(iod, PATIENT_ID, (SECRET,), "X/Z/D"),
        lambda iod: resolve_in_iod(iod, PATIENT_ID, (), SECRET),
    ],
)
def test_messages_repeat_no_value(tables, call):
    with pytest.raises(ValueError) as raised:
        call(tables.iods["CT Image"])

    assert SECRET not in str(raised.value)
    assert "Doe" not in repr(raised.value)
