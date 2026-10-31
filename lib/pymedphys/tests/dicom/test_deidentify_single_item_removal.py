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

"""Clean Structured Content removes a content item that cannot be kept on its own.

The item goes with everything in it, and so do the items that go with it: a
by-reference relationship to it, and a CONTAINER left with no items. A
Referenced Content Item Identifier (0040,DB73) that is kept is renumbered,
and the writer, the verification of what it preserved, and the check of the
IOD's requirements number the items as the output does.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``. Content items whose concept names Table E.3.4-1 does
not list are coded in the invented local scheme ``99PMP``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import policy, run
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.preservation import (
    Expectations,
    PreservationFailed,
    PreservationReason,
    verify_preservation,
)
from pymedphys._dicom.deidentify.preserving_writer import write_data_set
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.removed_items import RemovedItems
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_dose_reports as reports
from . import _synthetic_references as synthetic
from .test_deidentify_content_items import (
    ACCESSION_NUMBER,
    CONTENT,
    CSC,
    PERSON_NAME,
    PERSON_OBSERVER_NAME,
    REFERENCED_CONTENT_ITEM,
    REPORT,
    SECTION,
    SENTINEL,
    _actions,
    _by_reference,
    _coded,
    _container,
    _item,
    _path,
    _report,
    _text,
    _transform,
)
from .test_deidentify_preserving_writer import (
    FIRST_BEAM,
    SECOND_BEAM,
    _plan,
    _with_source_meta,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

BEAMS = _path(tag="(300A,00B0)")
BEAM_NUMBER = "(300A,00C0)"
HAS_PROPERTIES = "HAS PROPERTIES"
HAS_CONCEPT_MOD = "HAS CONCEPT MOD"


def _removed():
    """Return a content item that every option set removes."""
    return _text(ACCESSION_NUMBER, f"{SENTINEL} ACCESSION")


def _with_child(item, *children):
    """Return ``item``, a content item that is not a CONTAINER, with children."""
    for child in children:
        child.RelationshipType = HAS_PROPERTIES
    item.ContentSequence = pydicom.Sequence(list(children))
    return item


def _at(*indices):
    """Return the item of the tree at ``indices``, each from 0."""
    return tuple((CONTENT, index) for index in indices)


def _reference_at(*indices):
    return _path(*_at(*indices), tag=REFERENCED_CONTENT_ITEM)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_by_reference_relationship_to_a_removed_item_is_removed_with_it():
    dataset = _report(_coded(), _removed(), _by_reference(1, 2), _coded())

    actions = _actions((CSC,), dataset, REPORT)

    assert dict(actions) == {_path(tag=CONTENT): "K"}
    assert actions.removed_items == {_at(1), _at(2)}
    assert not actions.renumbered


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_by_reference_relationship_inside_a_removed_item_names_nothing_kept():
    # The relationship goes with the item that holds it, whatever it names.
    removed = _with_child(_removed(), _by_reference(1, 1))
    dataset = _report(_coded(), removed, _coded())

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1)}
    assert not actions.renumbered


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_reference_to_an_item_after_a_removed_one_is_renumbered():
    dataset = _report(_coded(), _removed(), _coded(), _by_reference(1, 3))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1)}
    assert dict(actions.renumbered) == {_reference_at(3): (1, 2)}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_reference_is_renumbered_at_each_level_it_passes():
    section = _container(SECTION, _removed(), _coded(), _coded())
    dataset = _report(_removed(), section, _by_reference(1, 2, 3))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(0), _at(1, 0)}
    assert dict(actions.renumbered) == {_reference_at(2): (1, 1, 2)}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_reference_to_an_item_before_a_removed_one_is_unchanged():
    dataset = _report(_coded(), _by_reference(1, 1), _removed())

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(2)}
    assert not actions.renumbered


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_section_whose_items_are_all_removed_is_removed_up_the_tree():
    inner = _container(SECTION, _removed(), _removed())
    dataset = _report(_coded(), _container(SECTION, inner), _coded())

    actions = _actions((CSC,), dataset, REPORT)

    # Only the outermost item that goes is named; it holds the others.
    assert actions.removed_items == {_at(1)}
    assert dict(actions) == {_path(tag=CONTENT): "K"}
    assert not actions.emptied


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_section_left_with_an_item_is_kept():
    section = _container(SECTION, _removed(), _coded())
    dataset = _report(section)

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(0, 0)}
    assert dict(actions) == {_path(tag=CONTENT): "K", _path(*_at(0), tag=CONTENT): "K"}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_an_item_whose_items_are_all_removed_loses_its_content_sequence():
    dataset = _report(_with_child(_coded(), _removed(), _removed()), _coded())
    emptied = _path(*_at(0), tag=CONTENT)

    actions = _actions((CSC,), dataset, REPORT)

    # The emptied sequence holds the removed items, so none is named.
    assert actions.emptied == {emptied}
    assert not actions.removed_items
    assert emptied not in actions
    assert actions[_path(tag=CONTENT)] == "K"


def test_the_walker_removes_an_emptied_content_sequence_without_sequestering():
    dataset = _report(_with_child(_coded(), _removed()), _coded())
    source = read_source(synthetic.written(dataset))
    iod = load_iod_tables().iods[REPORT]
    rules = ElementRules(policy.compose_custom_policy([CSC]))
    actions = _actions((CSC,), dataset, REPORT)

    plan = plan_instance(source, rules, iod, actions)

    planned = {e.path: e for e in plan.elements}
    assert planned[_path(*_at(0), tag=CONTENT)].action == "X"
    assert not plan.sequestrations
    assert not plan.removed_items


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "items",
    [
        (_removed(),),
        (_removed(), _by_reference(1, 1)),
        (_container(SECTION, _removed()),),
    ],
    ids=["removed", "with-a-reference-to-it", "in-a-section"],
)
def test_a_root_left_with_no_items_takes_the_tree_out(items):
    assert not _actions((CSC,), _report(*items), REPORT)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "reference",
    [_by_reference(1, 9), _by_reference(2, 1), _by_reference(1, 0), _by_reference()],
    ids=["no-such-item", "not-from-the-root", "position-zero", "no-value"],
)
def test_a_reference_that_names_no_item_takes_the_tree_out_where_an_item_goes(
    reference,
):
    kept = _report(_coded(), reference)
    removing = _report(_coded(), _removed(), reference)

    assert _actions((CSC,), kept, REPORT)[_path(tag=CONTENT)] == "K"
    assert not _actions((CSC,), removing, REPORT)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_an_item_with_a_modifier_that_cannot_be_kept_is_removed():
    modified = _coded()
    modified.ContentItemModifierSequence = pydicom.Sequence([_removed()])
    dataset = _report(_coded(), modified)

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1)}


TABLE = ("TBL1", "99PMP", "Fixture table")
TABULATED_VALUES = "(0040,A801)"
CELL_VALUES = "(0040,A808)"


def _table(*references):
    """Return a TABLE whose cells, one row, each name an item of the tree.

    Each of ``references`` gives the positions of a cell's item, or ``None``
    for a cell with a value of its own.
    """
    cells = []
    for column, positions in enumerate(references, start=1):
        cell = pydicom.Dataset()
        cell.TableRowNumber = 1
        cell.TableColumnNumber = column
        if positions is None:
            cell.SelectorAttributeVR = "FD"
            cell.SelectorFDValue = 1.5
        else:
            cell.ReferencedContentItemIdentifier = list(positions)
        cells.append(cell)
    values = pydicom.Dataset()
    values.NumberOfTableRows = 1
    values.NumberOfTableColumns = len(references)
    values.CellValuesSequence = pydicom.Sequence(cells)
    return _item("TABLE", TABLE, TabulatedValuesSequence=pydicom.Sequence([values]))


def _cell(index, *at):
    """Return the TABLE cell, from 0, of the item at ``at``."""
    return (*_at(*at), (TABULATED_VALUES, 0), (CELL_VALUES, index))


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_table_cell_that_names_a_removed_item_is_removed_on_its_own():
    # PS3.3 Section C.18.10 lets a table be sparse, so the cell goes and
    # the table, with its other cells, is kept.
    dataset = _report(_coded(), _removed(), _table((1, 1), (1, 2), None))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1), _cell(1, 2)}
    assert dict(actions) == {_path(tag=CONTENT): "K"}
    assert not actions.renumbered


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_table_whose_cells_are_all_removed_is_removed():
    # Cell Values Sequence is Type 1, so a table with no cell goes, and so
    # does the reference to it.
    dataset = _report(_coded(), _removed(), _table((1, 2)), _by_reference(1, 3))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1), _at(2), _at(3)}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_table_cell_is_renumbered_as_a_reference_is():
    dataset = _report(_removed(), _coded(), _table((1, 2)))

    actions = _actions((CSC,), dataset, REPORT)

    reference = ElementPath(_cell(0, 2), REFERENCED_CONTENT_ITEM)
    assert actions.removed_items == {_at(0)}
    assert dict(actions.renumbered) == {reference: (1, 1)}


def _modifier():
    """Return a HAS CONCEPT MOD item that cannot be kept.

    Its concept name is coded in UMLS, whose rows the pin leaves out.
    """
    item = _item(
        "CODE",
        ("C0000001", "UMLS", "Fixture modifier"),
        ConceptCodeSequence=pydicom.Sequence([_coded().ConceptCodeSequence[0]]),
    )
    item.RelationshipType = HAS_CONCEPT_MOD
    return item


def _modified(item, *children):
    """Return ``item`` holding a modifier that cannot be kept, then ``children``."""
    item = _with_child(item, *children) if children else item
    item.ContentSequence = pydicom.Sequence(
        [_modifier(), *item.get("ContentSequence", [])]
    )
    return item


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_concept_modifier_that_cannot_be_kept_removes_the_item_it_modifies():
    # The item goes, with its other items, and so do the reference to it and
    # the section it leaves with no items.
    section = _container(SECTION, _modified(_coded(), _coded()))
    dataset = _report(_coded(), section, _by_reference(1, 2, 1))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(1), _at(2)}
    assert dict(actions) == {_path(tag=CONTENT): "K"}
    assert not actions.emptied


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_section_is_kept_without_a_concept_modifier_that_cannot_be_kept():
    section = _container(SECTION, _coded())
    section.ContentSequence.insert(0, _modifier())
    dataset = _report(section, _by_reference(1, 1, 2))

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(0, 0)}
    assert dict(actions) == {_path(tag=CONTENT): "K", _path(*_at(0), tag=CONTENT): "K"}
    assert dict(actions.renumbered) == {_reference_at(1): (1, 1, 1)}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_the_root_is_kept_without_a_concept_modifier_that_cannot_be_kept():
    dataset = _report(_modifier(), _coded())

    actions = _actions((CSC,), dataset, REPORT)

    assert actions.removed_items == {_at(0)}
    assert dict(actions) == {_path(tag=CONTENT): "K"}


def test_the_walker_removes_the_elements_of_a_removed_item_and_keeps_its_siblings():
    name = _item("PNAME", PERSON_OBSERVER_NAME, PersonName=f"{SENTINEL}^NAME")
    dataset = _report(_removed(), name, _by_reference(1, 2))
    source = read_source(synthetic.written(dataset))
    iod = load_iod_tables().iods[REPORT]
    rules = ElementRules(policy.compose_custom_policy([CSC]))
    actions = _actions((CSC,), dataset, REPORT)

    plan = plan_instance(source, rules, iod, actions)

    planned = {e.path: e for e in plan.elements}
    inside = [e for e in plan.elements if e.path.items[:1] == _at(0)]
    assert inside
    assert all(e.action == "X" and e.removed_item == _at(0) for e in inside)
    assert planned[_path(tag=CONTENT)].action == "K"
    assert planned[_path(*_at(1), tag=PERSON_NAME)].action == "D"
    assert planned[_reference_at(2)].action == "K"
    assert plan.removed_items == {_at(0)}
    assert dict(plan.renumbered) == {_reference_at(2): (1, 1)}
    assert not plan.sequestrations


def _dose_report(*appended):
    """Return an X-Ray Radiation Dose SR whose root also holds ``appended``.

    The report has only its required rows, before ``appended``.
    """
    dataset = reports.x_ray_dose_report(())
    for item in appended:
        if "RelationshipType" not in item:
            item.RelationshipType = "CONTAINS"
        dataset.ContentSequence.append(item)
    return dataset


def _transformed(dataset):
    data = synthetic.written(dataset)
    result = _transform((CSC,))(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    return pydicom.dcmread(io.BytesIO(result.data))


def _meaning(item):
    return item.ConceptNameCodeSequence[0].CodeMeaning


def _meanings(sequence):
    return [_meaning(item) for item in sequence if "ConceptNameCodeSequence" in item]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_written_table_keeps_the_cells_that_name_kept_items():
    first = len(reports.x_ray_dose_report(()).ContentSequence) + 1
    dataset = _dose_report(
        _removed(),
        _coded("Fixture kept"),
        _table((1, first), (1, first + 1), None),
    )

    written = _transformed(dataset)

    table = written.ContentSequence[-1]
    assert table.ValueType == "TABLE"
    assert _meaning(written.ContentSequence[-2]) == "Fixture kept"
    cells = table.TabulatedValuesSequence[0].CellValuesSequence
    assert [cell.TableColumnNumber for cell in cells] == [2, 3]
    assert list(cells[0].ReferencedContentItemIdentifier) == [1, first]
    assert cells[1].SelectorFDValue == 1.5


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_written_report_numbers_its_references_as_its_items():
    first = len(reports.x_ray_dose_report(()).ContentSequence) + 1
    dataset = _dose_report(
        _coded("Fixture before"),
        _removed(),
        _by_reference(1, first + 1),
        _coded("Fixture after"),
        _by_reference(1, first + 3),
    )

    written = _transformed(dataset)

    meanings = _meanings(written.ContentSequence)
    assert "Accession Number" not in meanings
    assert meanings[-2:] == ["Fixture before", "Fixture after"]
    (reference,) = (
        item
        for item in written.ContentSequence
        if "ReferencedContentItemIdentifier" in item
    )
    _, position = reference.ReferencedContentItemIdentifier
    assert _meaning(written.ContentSequence[position - 1]) == "Fixture after"


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_written_report_leaves_out_a_content_sequence_whose_items_are_removed():
    dataset = _dose_report(_with_child(_coded("Fixture parent"), _removed()))

    written = _transformed(dataset)

    parent = written.ContentSequence[-1]
    assert _meaning(parent) == "Fixture parent"
    assert "ContentSequence" not in parent


def _source_and_plan():
    """Return an RT Plan-like source, and a plan that removes its first beam."""
    source = read_source(_plan())
    removed = frozenset(p for p in source.paths() if p.items[:1] == (FIRST_BEAM,))
    kept = frozenset(source.paths()) - removed
    return source, kept, removed


def test_the_writer_removes_an_item_on_its_own():
    source, kept, removed = _source_and_plan()
    removed_items = frozenset({(FIRST_BEAM,)})

    written = write_data_set(
        source,
        kept=kept,
        removed=removed,
        replacements={},
        removed_items=removed_items,
    )

    data = _with_source_meta(_plan(), source, written)
    output = read_source(data)
    verify_preservation(
        source,
        output,
        Expectations(kept=kept, removed=removed, removed_items=removed_items),
    )
    (beam,) = pydicom.dcmread(io.BytesIO(data)).BeamSequence
    assert beam.BeamNumber == 2


@pytest.mark.parametrize(
    "item, kept_too",
    [
        # Not an item of a kept sequence.
        ((("(0008,1140)", 0), ("(300A,00B0)", 0)), False),
        # Beyond the sequence's items.
        ((("(300A,00B0)", 2),), False),
        # An element in it is kept.
        ((FIRST_BEAM,), True),
    ],
    ids=["no-such-sequence", "no-such-item", "holds-a-kept-element"],
)
def test_the_writer_rejects_an_item_it_cannot_remove(item, kept_too):
    source, kept, removed = _source_and_plan()
    if kept_too:
        removed = frozenset()
        kept = frozenset(source.paths())

    with pytest.raises(ValueError):
        write_data_set(
            source,
            kept=kept - removed,
            removed=removed,
            replacements={},
            removed_items=frozenset({item}),
        )


def test_an_output_that_keeps_a_removed_item_is_refused():
    source, kept, removed = _source_and_plan()
    unchanged = read_source(_plan())

    with pytest.raises(PreservationFailed) as raised:
        verify_preservation(
            source,
            unchanged,
            Expectations(
                kept=kept, removed=removed, removed_items=frozenset({(FIRST_BEAM,)})
            ),
        )

    # The output's first beam is checked as the source's second.
    assert raised.value.reason is PreservationReason.UNEXPECTED
    assert raised.value.path.items == (SECOND_BEAM,)


def test_removed_items_map_paths_between_the_two_numberings():
    outer = ("(0040,A730)", 0)
    removed = RemovedItems({(outer,), (("(0040,A730)", 2),), (outer, SECOND_BEAM)})
    later = _path(("(0040,A730)", 3), ("(300A,00B0)", 0), tag=BEAM_NUMBER)
    nested = _path(("(0040,A730)", 1), ("(300A,00B0)", 2), tag=BEAM_NUMBER)

    assert removed.output_path(later) == _path(
        ("(0040,A730)", 1), ("(300A,00B0)", 0), tag=BEAM_NUMBER
    )
    # The beams removed inside the first item renumber nothing in another.
    assert removed.output_path(nested) == _path(
        ("(0040,A730)", 0), ("(300A,00B0)", 2), tag=BEAM_NUMBER
    )
    for path in (later, nested):
        output = removed.output_path(path)
        assert output is not None
        assert removed.source_path(output) == path
    assert removed.output_path(_path(outer, SECOND_BEAM, tag=BEAM_NUMBER)) is None
    assert removed.holds(_path(outer, tag=BEAM_NUMBER))
    assert not removed.holds(later)
    assert removed.count(_path(tag="(0040,A730)")) == 2
    assert removed.count(_path(outer, tag="(300A,00B0)")) == 1
    assert removed
    assert not RemovedItems()


def test_removed_items_need_a_sequence_and_an_index():
    with pytest.raises(ValueError):
        RemovedItems({()})


def test_the_paths_of_no_removed_items_are_the_same_in_both_numberings():
    path = ElementPath((FIRST_BEAM,), BEAM_NUMBER)

    assert RemovedItems().output_path(path) == path
    assert RemovedItems().source_path(path) == path
