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

"""The synthetic corpus, its markers, and its manifest."""

import collections
import json
import re

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import elements, standard
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.reference_graph import build_reference_graph
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.sop_classes import iod_for_sop_class
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.values import value_problem, values_problem

pytestmark = pytest.mark.pydicom

Kind = corpus_module.PlacementKind
Reason = corpus_module.NotPlantedReason
IMPLICIT = "1.2.840.10008.1.2"
EXPLICIT = "1.2.840.10008.1.2.1"
# The kinds whose values no other placement holds.
UNIQUE_KINDS = frozenset({Kind.PLANTED, Kind.CONTENT, Kind.PRIVATE, Kind.UN_ENCODED})
TEXT = r"SYNMK-\d{5}"
# The conspicuous form of a marker of each VR, written out independently.
MARKER_PATTERNS = {
    **dict.fromkeys(("AE", "LO", "LT", "SH", "ST", "UC", "UT", "UN", "OB", "OW"), TEXT),
    "AS": r"\d{3}W",
    "CS": r"SYNMK_\d{5}",
    "DA": r"18\d\d(0[1-9]|1[0-2])\d\d",
    "DS": r"8\d{5}\.5",
    "DT": r"18\d\d(0[1-9]|1[0-2])\d{8}",
    "IS": r"7\d{5}",
    "PN": r"SYNMK(\d{5})\^M[AÄ]RKER\1",
    "TM": r"\d{6}",
    "UI": r"2\.25\.99999\d{5}",
    "UR": r"https://synmk\.invalid/SYNMK-\d{5}",
    "US": r"\d{1,5}",
}
LINKED_PATTERNS = {
    Kind.LINKED_UID: r"2\.25\.88888\d{5}",
    Kind.LINKED_PATIENT: r"SYNMK-LINKED-(PATIENT|ISSUER)",
}


@pytest.fixture(name="corpus", scope="module")
def fixture_corpus():
    return corpus_module.build_corpus()


def _placements(corpus, *kinds):
    """Yield each file and placement of the given kinds, or of every kind."""
    for file in corpus.files:
        for placement in file.manifest.placements:
            if not kinds or placement.kind in kinds:
                yield file, placement


def _profile_rows():
    rows = standard.load_table_e1_1().attributes
    return [row.tag for row in rows if row.tag != standard.PRIVATE_ATTRIBUTES_TAG]


def _expected_places(iod):
    """Return each path and tag where the IOD defines an attribute of Table E.1-1."""
    rows = _profile_rows()
    exact = set(rows)
    masked = [row for row in rows if "x" in row]

    def covered(tag):
        return tag in exact or any(
            len(mask) == len(tag) and all(m in ("x", t) for m, t in zip(mask, tag))
            for mask in masked
        )

    return {
        (definition.path, definition.tag)
        for definition in iod.definitions
        if covered(definition.tag)
    }


class _Reader:
    """Read the elements of one file through the engine's decoder."""

    def __init__(self, data):
        self.evidence = read_source(data)
        dataset = self.evidence.dataset()
        codecs = elements.dataset_codecs(dataset, source=self.evidence)
        self._items = {(): (dataset, codecs, ())}

    def _item(self, within):
        if within not in self._items:
            dataset, codecs, ancestors = self._item(within[:-1])
            tag, index = within[-1]
            sequence = elements.read_element(
                dataset,
                ElementPath(within[:-1], tag),
                codecs,
                ancestors,
                source=self.evidence,
            )
            item = sequence.items[index]
            codecs = elements.dataset_codecs(item, codecs, within, source=self.evidence)
            self._items[within] = (item, codecs, (dataset, *ancestors))
        return self._items[within]

    def read(self, path):
        dataset, codecs, ancestors = self._item(path.items)
        return elements.read_element(
            dataset, path, codecs, ancestors, source=self.evidence
        )


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("ascii").rstrip("\x00 ")
    return str(value)


def test_two_builds_are_byte_identical(corpus):
    again = corpus_module.build_corpus()

    assert [file.data for file in again.files] == [file.data for file in corpus.files]
    assert again.manifest == corpus.manifest
    assert again.manifest.to_json() == corpus.manifest.to_json()


def test_the_build_is_the_same_with_pydicoms_future_behaviour(
    corpus, pydicom_behaviour
):
    del pydicom_behaviour  # the build runs under each behaviour

    again = corpus_module.build_corpus()

    assert [file.data for file in again.files] == [file.data for file in corpus.files]


def test_files_have_deterministic_names_and_the_linked_collection(corpus):
    assert [file.name for file in corpus.files] == [
        "01-ct-1.dcm",
        "02-ct-2.dcm",
        "03-ct-3.dcm",
        "04-rtstruct.dcm",
        "05-rtplan.dcm",
        "06-rtdose.dcm",
    ]
    assert [file.manifest.iod for file in corpus.files] == [
        "CT Image",
        "CT Image",
        "CT Image",
        "RT Structure Set",
        "RT Plan",
        "RT Dose",
    ]


def test_every_attribute_of_table_e1_1_that_the_iod_defines_is_placed(corpus):
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        expected = _expected_places(iod)
        found = collections.Counter()
        for placement in file.manifest.placements:
            path = placement.path
            if placement.kind is Kind.PRIVATE or placement.kind is Kind.CONTENT:
                continue
            if any(index for _, index in path.items):
                # The structure set's references to the other slices.
                assert placement.kind is Kind.LINKED_UID
                continue
            # A repeating group is planted in its first group.
            tag = re.sub(r"^\((50|60)00,", r"(\1xx,", path.tag)
            if (tuple(each for each, _ in path.items), tag) not in expected:
                tag = path.tag
            found[tuple(each for each, _ in path.items), tag] += 1
            assert (placement.reason is None) == (
                placement.kind is not Kind.NOT_PLANTED
            )

        assert set(found) == expected, file.name
        assert max(found.values()) == 1, file.name


def test_attributes_are_not_planted_only_beyond_the_depth_cap(corpus):
    reasons = collections.Counter()
    for file in corpus.files:
        placed = file.manifest.placements
        planted_tags = {p.path.tag for p in placed if p.kind is not Kind.NOT_PLANTED}
        for placement in placed:
            depth = len(placement.path.items)
            if placement.kind is Kind.NOT_PLANTED:
                reasons[placement.reason] += 1
                assert placement.values == ()
                assert depth + (placement.vr == "SQ") > corpus_module.MAX_DEPTH
                # Each attribute capped is planted at a shallower place.
                assert placement.path.tag in planted_tags
            else:
                assert depth <= corpus_module.MAX_DEPTH

    assert set(reasons) == {Reason.DEPTH_CAP}


def test_markers_are_unique_and_conspicuous(corpus):
    seen = collections.Counter()
    for _, placement in _placements(corpus, *UNIQUE_KINDS):
        assert placement.values, placement
        for value in placement.values:
            assert re.fullmatch(MARKER_PATTERNS[placement.vr], value), placement
            seen[value] += 1
    for kind, pattern in LINKED_PATTERNS.items():
        for _, placement in _placements(corpus, kind):
            assert re.fullmatch(pattern, placement.values[0]), placement

    assert seen and max(seen.values()) == 1
    numbers = [
        int(match.group(1))
        for value in seen
        if (match := re.search(r"SYNMK[-_]?(\d{5})", value))
    ]
    assert len(numbers) == len(set(numbers))


def test_dates_are_distinct_valid_nineteenth_century_dates(corpus):
    dates = [
        value[:8]
        for _, placement in _placements(corpus, Kind.PLANTED)
        if placement.vr in ("DA", "DT")
        for value in placement.values
    ]

    assert dates and len(dates) == len(set(dates))
    assert all(value_problem("DA", date) is None for date in dates)
    assert all(date.startswith("18") for date in dates)


def test_values_read_back_and_are_valid_for_their_vr_and_vm(corpus):
    for file in corpus.files:
        reader = _Reader(file.data)
        for placement in file.manifest.placements:
            if placement.kind in (Kind.NOT_PLANTED, Kind.PRIVATE, Kind.UN_ENCODED):
                continue
            attribute = standard.dictionary_attribute(placement.path.tag)
            element = reader.read(placement.path)
            if placement.kind is Kind.SEQUENCE:
                assert element.vr == "SQ" and len(element.items) >= 1
                continue
            values = [_as_text(value) for value in element.values]

            assert tuple(values) == placement.values, placement.path
            assert element.vr == placement.vr
            assert values_problem(attribute.vr, attribute.vm, element.values) is None


def test_binary_private_and_un_values_hold_their_marker(corpus):
    for file, placement in _placements(corpus, Kind.PRIVATE, Kind.UN_ENCODED):
        evidence = read_source(file.data)
        field = evidence.value_field(placement.path)
        (text,) = placement.values

        assert field.rstrip(b"\x00 ") == text.encode("ascii")
        assert values_problem(placement.vr, "1", [text]) is None or (
            placement.vr == "UN"
        )


def test_every_file_is_admitted_by_the_strict_reader(corpus):
    for file in corpus.files:
        evidence = read_source(file.data)
        for placement in file.manifest.placements:
            assert (placement.path in evidence) == (
                placement.kind is not Kind.NOT_PLANTED
            ), placement


def test_the_reference_graph_has_no_findings(corpus):
    graph = build_reference_graph(
        [InstanceRecord.from_file(file.data) for file in corpus.files]
    )

    assert not graph.findings
    targets = {(edge.source, edge.target) for edge in graph.edges}
    # The structure set references every slice, the plan the structure set
    # and the dose, and the dose the plan.
    assert {(3, 0), (3, 1), (3, 2), (4, 3), (4, 5), (5, 4)} <= targets


def test_one_instance_is_in_implicit_vr_and_the_rest_explicit(corpus):
    syntaxes = {
        file.name: read_source(file.data).transfer_syntax for file in corpus.files
    }

    assert syntaxes == {
        file.name: file.manifest.transfer_syntax for file in corpus.files
    }
    assert [name for name, syntax in syntaxes.items() if syntax == IMPLICIT] == [
        "06-rtdose.dcm"
    ]
    assert set(syntaxes.values()) == {IMPLICIT, EXPLICIT}


def test_an_element_is_encoded_as_un_in_explicit_vr(corpus):
    found = list(_placements(corpus, Kind.UN_ENCODED))

    assert len(found) == 1
    file, placement = found[0]
    evidence = read_source(file.data)
    assert evidence.transfer_syntax == EXPLICIT
    assert evidence.element(placement.path).vr == "UN"
    assert placement.path == ElementPath((), "(0010,4000)")
    assert placement.profile_tag == "(0010,4000)"


def test_each_file_has_private_blocks_at_the_top_level_and_in_an_item(corpus):
    for file in corpus.files:
        private = [
            placement
            for placement in file.manifest.placements
            if placement.kind is Kind.PRIVATE
        ]
        evidence = read_source(file.data)
        creators = [p for p in private if p.path.tag.endswith(",0010)")]

        assert {len(p.path.items) for p in creators} == {0, 1}
        assert all(int(p.path.tag[1:5], 16) % 2 for p in private)
        assert all(p.profile_tag == standard.PRIVATE_ATTRIBUTES_TAG for p in private)
        for placement in private:
            extent = evidence.element(placement.path)
            implicit = evidence.transfer_syntax == IMPLICIT
            assert extent.vr == (None if implicit else placement.vr)


def test_the_structure_set_has_a_second_character_set(corpus):
    (structure_set,) = [
        file for file in corpus.files if file.manifest.iod == "RT Structure Set"
    ]
    reader = _Reader(structure_set.data)
    path = ElementPath((), "(0010,0010)")
    element = reader.read(path)
    (placement,) = [p for p in structure_set.manifest.placements if p.path == path]

    assert structure_set.manifest.specific_character_set == "ISO_IR 100"
    assert element.codecs == ("latin_1",)
    assert not str(element.values[0]).isascii()
    assert str(element.values[0]) == placement.values[0]
    assert "Ä".encode("latin-1") in structure_set.data
    others = [file for file in corpus.files if file is not structure_set]
    assert all(not file.manifest.specific_character_set for file in others)


def test_sequences_hold_a_marker_unless_the_iod_defines_nothing_in_them(corpus):
    empty = []
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        placed = file.manifest.placements
        for sequence in placed:
            if sequence.kind is not Kind.SEQUENCE:
                continue
            inside = (*sequence.path.items, (sequence.path.tag, 0))
            below = [
                p
                for p in placed
                if p.path.items[: len(inside)] == inside
                and p.kind is not Kind.NOT_PLANTED
            ]
            if not below:
                path = tuple(tag for tag, _ in inside)
                assert not [d for d in iod.definitions if d.path == path], path
                empty.append(sequence.path.tag)
        for content in (p for p in placed if p.kind is Kind.CONTENT):
            assert any(
                p.kind is Kind.SEQUENCE
                and (*p.path.items, (p.path.tag, 0)) == content.path.items
                for p in placed
            ), content.path

    # Modified Attributes Sequence, whose item holds any attribute modified.
    assert set(empty) == {"(0400,0550)"}


def test_the_manifest_json_is_deterministic_and_has_every_placement(corpus):
    text = corpus.manifest.to_json()
    document = json.loads(text)

    assert text == corpus_module.build_corpus().manifest.to_json()
    assert text.isascii()
    assert document["max_depth"] == corpus_module.MAX_DEPTH
    assert [each["name"] for each in document["files"]] == [
        file.name for file in corpus.files
    ]
    for each, file in zip(document["files"], corpus.files):
        assert each["placements"] == [
            placement.to_dict() for placement in file.manifest.placements
        ]
        assert len(each["placements"]) == len(file.manifest.placements)
        for record in each["placements"]:
            assert set(record) == {
                "items",
                "tag",
                "vr",
                "values",
                "kind",
                "profile_tag",
                "reason",
            }


def test_the_corpus_is_written_only_to_a_new_place(corpus, tmp_path):
    written = corpus_module.write_corpus(corpus, tmp_path)

    assert [path.name for path in written] == [
        *(file.name for file in corpus.files),
        "manifest.json",
    ]
    assert [path.read_bytes() for path in written[:-1]] == [
        file.data for file in corpus.files
    ]
    assert written[-1].read_text(encoding="utf-8") == corpus.manifest.to_json()
    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)


def test_the_repr_shows_no_file_bytes(corpus):
    assert "data=" not in repr(corpus.files[0])
