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
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    elements,
    icc_profiles,
    scope,
    standard,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import (
    ElementPath,
    Region,
    read_file_layout,
)
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
    "TM": r"([01]\d|2[0-3])[0-5]\d[0-5]\d\.424242",
    "UI": r"2\.25\.99999\d{5}",
    "UR": r"https://synmk\.invalid/SYNMK-\d{5}",
    "US": r"[1-9]\d{0,4}",
}
# The text VRs, whose markers are searched for as bytes.
TEXT_VRS = frozenset(MARKER_PATTERNS) - {"OB", "OW", "UN", "US"}
REFERENCED_SOP_CLASS = "(0008,1150)"
REFERENCED_SOP_INSTANCE = "(0008,1155)"
# The kinds that leave a value that the residual search can find.
MARKERS = frozenset({Kind.PLANTED, Kind.CONTENT})
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
        "07-rtdose-review.dcm",
        "08-ct-enhanced.dcm",
        "09-ct-legacy-enhanced.dcm",
        "10-mr.dcm",
        "11-mr-enhanced.dcm",
        "12-mr-enhanced-color.dcm",
        "13-mr-legacy-enhanced.dcm",
        "14-mr-spectroscopy.dcm",
        "15-pet.dcm",
        "16-pet-enhanced.dcm",
        "17-pet-legacy-enhanced.dcm",
    ]
    assert [file.manifest.iod for file in corpus.files] == [
        "CT Image",
        "CT Image",
        "CT Image",
        "RT Structure Set",
        "RT Plan",
        "RT Dose",
        "RT Dose",
        "Enhanced CT Image",
        "Legacy Converted Enhanced CT Image",
        "MR Image",
        "Enhanced MR Image",
        "Enhanced MR Color Image",
        "Legacy Converted Enhanced MR Image",
        "MR Spectroscopy",
        "Positron Emission Tomography Image",
        "Enhanced PET Image",
        "Legacy Converted Enhanced PET Image",
    ]
    # Every IOD of the first supported release.
    assert {file.manifest.iod for file in corpus.files} == scope.SUPPORTED_IODS


def test_every_attribute_of_table_e1_1_that_the_iod_defines_is_placed(corpus):
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        expected = _expected_places(iod)
        found = collections.Counter()
        for placement in file.manifest.placements:
            path = placement.path
            if placement.kind in (Kind.PRIVATE, Kind.CONTENT, Kind.REVIEW_COPY):
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
            if placement.kind is Kind.NOT_PLANTED:
                assert placement.reason is not None
            elif placement.kind is Kind.SEQUENCE:
                assert placement.reason in (None, Reason.NO_MARKER_CARRIER)
            else:
                assert placement.reason is None

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
                if placement.reason is Reason.SEQUESTERS_INSTANCE:
                    continue
                assert depth + (placement.vr == "SQ") > corpus_module.MAX_DEPTH
                # Each attribute capped is planted at a shallower place.
                assert placement.path.tag in planted_tags
            else:
                assert depth <= corpus_module.MAX_DEPTH

    assert set(reasons) == {Reason.DEPTH_CAP, Reason.SEQUESTERS_INSTANCE}


def _sequesters(iod, placement):
    """Return whether the Basic Profile's plain X on a placement sequesters."""
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    path = tuple(tag for tag, _ in placement.path.items)
    return rows[placement.profile_tag].basic_profile == "X" and (
        compound_actions.resolve_plain_x_in_iod(iod, placement.path.tag, path).extent
        is compound_actions.RemovalExtent.SEQUESTER
    )


def test_an_attribute_whose_removal_sequesters_is_planted_in_one_instance(corpus):
    planted = collections.defaultdict(set)
    withheld = collections.defaultdict(set)
    for file, placement in _placements(corpus, Kind.PLANTED, Kind.NOT_PLANTED):
        iod = iod_for_sop_class(file.manifest.sop_class)
        if placement.reason is Reason.SEQUESTERS_INSTANCE:
            assert _sequesters(iod, placement), placement
            withheld[file.name].add(placement.path.tag)
        elif placement.kind is Kind.PLANTED and _sequesters(iod, placement):
            planted[file.name].add(placement.path.tag)

    # Responsible Person and Responsible Organization (D-020), only in the
    # third slice, so that the other instances can be released; and the
    # Enhanced PET Image's Radiopharmaceutical Start DateTime, in no file.
    both = {"(0010,2297)", "(0010,2299)"}
    assert planted == {corpus_module.SEQUESTERED_FILE: both}
    assert corpus_module.SEQUESTERED_FILE == corpus.files[2].name
    assert withheld == {
        file.name: (
            both | {"(0018,1078)"}
            if file.manifest.iod == "Enhanced PET Image"
            else both
        )
        for file in corpus.files
        if file.name != corpus_module.SEQUESTERED_FILE
    }


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
            # The invalid UID marker is checked in its own test.
            if placement.kind in (
                Kind.NOT_PLANTED,
                Kind.PRIVATE,
                Kind.UN_ENCODED,
                Kind.INVALID,
            ):
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
    # and the dose, and each dose the plan.
    assert {(3, 0), (3, 1), (3, 2), (4, 3), (4, 5), (5, 4), (6, 4)} <= targets
    # The MR and PET Images reference the first slice, and each other
    # instance the single-frame one of its modality.
    names = [file.name for file in corpus.files]
    position = names.index
    sources = {
        "08-ct-enhanced.dcm": "01-ct-1.dcm",
        "09-ct-legacy-enhanced.dcm": "01-ct-1.dcm",
        "10-mr.dcm": "01-ct-1.dcm",
        "11-mr-enhanced.dcm": "10-mr.dcm",
        "12-mr-enhanced-color.dcm": "10-mr.dcm",
        "13-mr-legacy-enhanced.dcm": "10-mr.dcm",
        "14-mr-spectroscopy.dcm": "10-mr.dcm",
        "15-pet.dcm": "01-ct-1.dcm",
        "16-pet-enhanced.dcm": "15-pet.dcm",
        "17-pet-legacy-enhanced.dcm": "15-pet.dcm",
    }
    assert {
        (position(source), position(target)) for source, target in sources.items()
    } <= targets


def test_two_instances_are_in_implicit_vr_and_the_rest_explicit(corpus):
    syntaxes = {
        file.name: read_source(file.data).transfer_syntax for file in corpus.files
    }

    assert syntaxes == {
        file.name: file.manifest.transfer_syntax for file in corpus.files
    }
    assert [name for name, syntax in syntaxes.items() if syntax == IMPLICIT] == [
        "06-rtdose.dcm",
        "10-mr.dcm",
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


def test_sequences_hold_a_marker_unless_their_item_can_hold_none(corpus):
    without = set()
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        placed = file.manifest.placements
        for sequence in placed:
            if sequence.kind is not Kind.SEQUENCE:
                continue
            inside = (*sequence.path.items, (sequence.path.tag, 0))
            # Linked UIDs survive a preset that keeps the sequence and
            # remaps its UIDs, so only a marker counts.
            below = [
                p
                for p in placed
                if p.path.items[: len(inside)] == inside and p.kind in MARKERS
            ]
            if below:
                assert sequence.reason is None, sequence.path
                continue
            assert sequence.reason is Reason.NO_MARKER_CARRIER, sequence.path
            path = tuple(tag for tag, _ in inside)
            for definition in iod.definitions:
                if definition.path == path and "x" not in definition.tag:
                    attribute = standard.dictionary_attribute(definition.tag)
                    assert attribute.vr in ("SQ", "UI") or len(attribute.vrs) > 1
            without.add(sequence.path.tag)
        for content in (p for p in placed if p.kind is Kind.CONTENT):
            assert any(
                p.kind is Kind.SEQUENCE
                and (*p.path.items, (p.path.tag, 0)) == content.path.items
                for p in placed
            ), content.path

    # Modified Attributes Sequence, whose item holds any attribute modified,
    # and the reference sequences whose items hold only UIDs.
    assert {
        "(0400,0550)",
        "(0008,1110)",
        "(0008,1111)",
        "(0008,1120)",
        "(0008,1140)",
    } <= without


def test_the_manifest_json_is_deterministic_and_matches_the_files(corpus):
    text = corpus.manifest.to_json()
    document = json.loads(text)

    assert text == corpus_module.build_corpus().manifest.to_json()
    assert text.isascii()
    assert document["max_depth"] == corpus_module.MAX_DEPTH
    assert [each["name"] for each in document["files"]] == [
        file.name for file in corpus.files
    ]
    for each, file in zip(document["files"], corpus.files):
        reader = _Reader(file.data)
        assert each["transfer_syntax"] == reader.evidence.transfer_syntax
        assert len(each["placements"]) == len(file.manifest.placements)
        for record in each["placements"]:
            path = ElementPath(
                tuple((tag, index) for tag, index in record["items"]), record["tag"]
            )
            if record["kind"] == "not-planted":
                assert path not in reader.evidence
                assert record["reason"] and not record["values"]
                continue
            if record["kind"] in ("private", "un-encoded", "invalid"):
                field = reader.evidence.value_field(path)
                assert field.rstrip(b"\x00 ").decode("ascii") == record["values"][0]
                continue
            element = reader.read(path)
            assert element.vr == record["vr"]
            assert [_as_text(value) for value in element.values] == record["values"]


def test_the_corpus_is_written_only_to_a_new_place(corpus, tmp_path):
    written = corpus_module.write_corpus(corpus, tmp_path)
    instances = tmp_path / corpus_module.INSTANCES_DIRECTORY

    assert written == (
        *(instances / file.name for file in corpus.files),
        tmp_path / "manifest.json",
    )
    assert [path.read_bytes() for path in written[:-1]] == [
        file.data for file in corpus.files
    ]
    assert written[-1].read_text(encoding="utf-8") == corpus.manifest.to_json()
    # The directory of instances, the input of a run, holds no manifest.
    assert sorted(path.name for path in instances.iterdir()) == [
        file.name for file in corpus.files
    ]
    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)


def test_the_repr_shows_no_file_bytes(corpus):
    assert "data=" not in repr(corpus.files[0])


def test_every_defined_length_is_even(corpus):
    for file in corpus.files:
        layout = read_file_layout(file.data)
        checked = 0
        for extent in layout.elements:
            if extent.undefined_length:
                continue
            assert (extent.end - extent.value_start) % 2 == 0, (
                file.name,
                str(extent.location),
            )
            checked += 1
        # Nested elements are among those checked.
        assert any(
            extent.location.element.items
            for extent in layout.elements
            if extent.location.region is Region.DATA_SET
        )
        assert checked > 100


def test_each_text_marker_occurs_once_in_its_file(corpus):
    for file in corpus.files:
        codec = "latin-1" if file.manifest.specific_character_set else "ascii"
        for placement in file.manifest.placements:
            if placement.kind not in UNIQUE_KINDS or placement.vr not in TEXT_VRS:
                continue
            for value in placement.values:
                assert file.data.count(value.encode(codec)) == 1, (
                    file.name,
                    placement.path,
                )


def test_every_marker_number_fits_a_signed_short():
    # SS markers are the negated number.
    assert corpus_module.MAX_MARKERS <= 2**15


def test_every_planted_placement_covers_a_row_of_table_e1_1(corpus):
    rows = set(_profile_rows())
    for _, placement in _placements(corpus, Kind.PLANTED, Kind.SEQUENCE):
        assert placement.profile_tag in rows, placement.path


def test_every_reference_item_has_its_referenced_sop_class(corpus):
    for file in corpus.files:
        evidence = read_source(file.data)
        references = [
            p
            for p in file.manifest.placements
            if p.kind is Kind.LINKED_UID
            and p.path.items
            and p.path.tag == REFERENCED_SOP_INSTANCE
        ]
        assert references
        for placement in references:
            path = ElementPath(placement.path.items, REFERENCED_SOP_CLASS)
            assert path in evidence, (file.name, placement.path)


def test_patient_and_procedure_step_references_have_their_own_classes(corpus):
    reader = _Reader(corpus.files[0].data)
    expected = {
        "(0008,1120)": "1.2.840.10008.3.1.2.1.1",  # Detached Patient Management
        "(0008,1111)": "1.2.840.10008.3.1.2.3.3",  # Modality Performed Proc. Step
    }
    for sequence, sop_class in expected.items():
        items = ((sequence, 0),)
        target = reader.read(ElementPath(items, REFERENCED_SOP_INSTANCE)).values
        found = reader.read(ElementPath(items, REFERENCED_SOP_CLASS)).values

        assert found == (sop_class,)
        assert target[0] not in corpus_module.CT_SLICES


def test_the_items_private_block_is_in_a_sequence_pydicom_knows(corpus):
    for file in corpus.files:
        (creator,) = [
            p
            for p in file.manifest.placements
            if p.kind is Kind.PRIVATE and p.path.items and p.path.tag.endswith(",0010)")
        ]
        ((tag, _),) = creator.path.items
        number = int(tag[1:5] + tag[6:10], 16)
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))

        assert pydicom.datadict.dictionary_has_tag(number)
        assert dataset[number].VR == "SQ"


def test_the_corpus_is_not_written_over_an_existing_file(corpus, tmp_path):
    instances = tmp_path / corpus_module.INSTANCES_DIRECTORY
    instances.mkdir()
    existing = instances / corpus.files[2].name
    existing.write_bytes(b"kept")

    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)

    assert existing.read_bytes() == b"kept"
    assert [path.name for path in instances.iterdir()] == [existing.name]
    assert [path.name for path in tmp_path.iterdir()] == [instances.name]


def test_the_corpus_is_not_written_beside_an_existing_manifest(corpus, tmp_path):
    existing = tmp_path / "manifest.json"
    existing.write_text("kept", encoding="utf-8")

    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)

    assert existing.read_text(encoding="utf-8") == "kept"
    assert [path.name for path in tmp_path.iterdir()] == [existing.name]


def test_a_second_dose_keeps_a_copy_of_a_marker_the_profile_replaces(corpus):
    names = [file.name for file in corpus.files]
    review = corpus.files[names.index(corpus_module.REVIEW_FILE)]
    plan = corpus.files[names.index("05-rtplan.dcm")]
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}

    (copy,) = [p for p in review.manifest.placements if p.kind is Kind.REVIEW_COPY]
    (label,) = [
        p
        for p in plan.manifest.placements
        if p.path == ElementPath((), "(300A,0002)") and p.kind is Kind.PLANTED
    ]
    # Manufacturer's Model Name, which Table E.1-1 does not list, holds the
    # plan's RT Plan Label, which the Basic Profile replaces.
    assert copy.path == ElementPath((), "(0008,1090)")
    assert copy.path.tag not in rows
    assert rows["(300A,0002)"].basic_profile == "D"
    assert copy.vr == "LO" and copy.values == label.values
    assert copy.profile_tag == ""
    assert [_as_text(v) for v in _Reader(review.data).read(copy.path).values] == list(
        copy.values
    )
    # No other placement copies a marker.
    assert [p for _, p in _placements(corpus, Kind.REVIEW_COPY)] == [copy]


def test_one_uid_marker_is_invalid_for_its_vr(corpus):
    names = [file.name for file in corpus.files]
    plan = corpus.files[names.index("05-rtplan.dcm")]
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}

    (invalid,) = [p for _, p in _placements(corpus, Kind.INVALID)]
    assert invalid in plan.manifest.placements
    # Device UID, which the Basic Profile replaces.
    assert invalid.path == ElementPath((), "(0018,1002)")
    assert invalid.profile_tag == "(0018,1002)"
    assert rows["(0018,1002)"].basic_profile == "U"
    (value,) = invalid.values
    assert re.fullmatch(r"2\.25\." + TEXT, value) and len(value) % 2 == 0
    assert value_problem("UI", value) is not None
    # Its marker is in no other placement, and nowhere else in its file.
    (number,) = re.findall(r"SYNMK-(\d{5})", value)
    others = {
        found
        for _, placement in _placements(corpus, *UNIQUE_KINDS)
        for text in placement.values
        for found in re.findall(r"(?:SYNMK|MARKER|99999)[-_]?(\d{5})", text)
    }
    assert others and number not in others
    assert plan.data.count(value.encode()) == 1
    # The strict reader admits it, and pydicom finds it invalid and quotes it.
    evidence = read_source(plan.data)
    assert evidence.value_field(invalid.path).rstrip(b"\x00").decode() == value
    with pytest.raises(ValueError, match=re.escape(value)):
        pydicom.valuerep.validate_value("UI", value, pydicom.config.RAISE)


def test_building_emits_no_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        corpus_module.build_corpus()


def test_each_image_has_its_frames_and_the_colour_image_its_icc_profile(corpus):
    frames = {}
    for file in corpus.files:
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
        if "PixelData" not in dataset:
            continue
        count = int(dataset.get("NumberOfFrames", 1))
        frames[file.manifest.iod] = count
        size = dataset.Rows * dataset.Columns * dataset.SamplesPerPixel
        assert len(dataset.PixelData) == count * size * dataset.BitsAllocated // 8

        if file.manifest.iod == "Enhanced MR Color Image":
            assert dataset.PhotometricInterpretation == "RGB"
            assert dataset.ICCProfile == icc_profiles.srgb_profile(
                corpus_module.SOURCE_ICC_DESCRIPTION
            )
            assert corpus_module.MARKER_PREFIX.encode() in dataset.ICCProfile
        else:
            assert dataset.PhotometricInterpretation == "MONOCHROME2"
            assert "ICCProfile" not in dataset

    # Every image but those of the single-frame IODs has two frames.
    assert {iod for iod, count in frames.items() if count == 1} == {
        "CT Image",
        "MR Image",
        "Positron Emission Tomography Image",
    }
    assert set(frames.values()) == {1, 2}


def test_the_spectroscopy_instance_holds_spectroscopy_data_only(corpus):
    (file,) = [f for f in corpus.files if f.manifest.iod == "MR Spectroscopy"]
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
    points = (
        dataset.Rows
        * dataset.Columns
        * int(dataset.NumberOfFrames)
        * dataset.DataPointRows
        * dataset.DataPointColumns
    )

    assert "PixelData" not in dataset
    assert dataset.DataRepresentation == "REAL"
    assert len(dataset.SpectroscopyData) == 4 * points
