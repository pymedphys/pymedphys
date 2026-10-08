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

"""Each preset run end to end over the synthetic corpus, searched for its markers.

The corpus (:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) plants a
conspicuous marker in each attribute of Table E.1-1 that its IODs define.
Under the Basic Profile every one of them is removed or replaced, so no
released file may hold any of them. The search here is independent of the
engine's own residual search: it looks for each recorded value as bytes,
and checks numeric values, which cannot be searched for, at their place.

Under ``basic-clean-descriptors`` every marker is removed or replaced as
under ``basic``: each attribute given C other than ROI Name takes its Basic
Profile action, and the structure set's one ROI Name, a marker, is mapped by
a reviewer's decision in the reviewed-names list. The run's structure set
also has a second ROI, added here, whose name the automatic tier writes in
the vocabulary's spelling. The vocabulary is invented and treated as a
published edition for these tests, so nothing is downloaded.

Under ``basic`` the corpus also runs with its images compressed, each in a
transfer syntax that encapsulates Pixel Data, with a marker planted in the
comment and application segments of its codestreams
(:func:`~pymedphys.tests.dicom._synthetic_compressed.compressed_corpus`): the
same instances are released, with their transfer syntax and pixels kept and
none of those markers.
"""

import dataclasses
import logging
import shutil
import tempfile
import warnings
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import roi_names, run, standard
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reasons import HeldRoiName
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._dicom.deidentify.run_report import (
    CONFORMANCE_STATEMENT,
    RELEASE_REPORT,
    RELEASE_REPORT_MARKDOWN,
)
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration
from pymedphys._dicom.deidentify.written_references import WrittenFindingKind

from . import _synthetic_compressed as compressed

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
UNWRITTEN_TARGET = WrittenFindingKind.UNWRITTEN_TARGET
Kind = corpus_module.PlacementKind
# The kinds whose values the Basic Profile removes or replaces.
REMOVED_KINDS = frozenset(Kind) - {
    Kind.SEQUENCE,
    Kind.NOT_PLANTED,
    Kind.REVIEW_COPY,
}
# Values of these VRs are numbers or ages, which occur throughout files, so
# they are checked at their place. Those held as text, DS and IS, are also
# searched for.
NUMERIC_VRS = frozenset(
    {"AS", "AT", "DS", "FD", "FL", "IS", "SL", "SS", "SV", "UL", "US", "UV"}
)
NUMBERS_AS_TEXT = frozenset({"DS", "IS"})
# Shorter forms would match by chance.
SHORTEST_FORM = 4
DATE_DIGITS = 8
# The generic parts of every marker.
MARKER_SIGNATURES = (
    corpus_module.MARKER_PREFIX,
    corpus_module.MARKER_UID_ROOT,
    corpus_module.LINKED_UID_ROOT,
    ".424242",
    "MARKER",
    "synmk.invalid",
)


CLEAN_DESCRIPTORS = "basic-clean-descriptors"
# The basic preset over the corpus with its images compressed, and text
# planted in their codestreams' metadata segments.
COMPRESSED = "basic-compressed"
BASIC_PROFILE_CODE = ("113100", "DCM")
CLEAN_DESCRIPTORS_CODE = ("113105", "DCM")
ROI_SEQUENCE = "(3006,0020)"
ROI_NAME = "(3006,0026)"
# The second ROI's name, which the automatic tier renames, and what it and
# the reviewer write.
UNCLEANED_NAME = "lung l"
VOCABULARY_NAME = "Lung_L"
MAPPED_NAME = "GTV_Primary"
VOCABULARY = tg263.Nomenclature(
    source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
    attribution=tg263.ATTRIBUTION,
    structures=(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Invented",
            minor_category="",
            anatomic_group="",
            primary_name=VOCABULARY_NAME,
            reverse_order_name="L_Lung",
            description="",
            fma_id=None,
        ),
    ),
)


@pytest.fixture(name="published", scope="module")
def fixture_published():
    """Treat the invented vocabulary as a published edition."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
        )
        yield


@pytest.fixture(
    name="preset_run", scope="module", params=["basic", CLEAN_DESCRIPTORS, COMPRESSED]
)
def fixture_preset_run(request, published):  # pylint: disable = unused-argument
    corpus = corpus_module.build_corpus()
    if request.param == COMPRESSED:
        yield _run(compressed.compressed_corpus(corpus), "basic")
    elif request.param == CLEAN_DESCRIPTORS:
        corpus = _with_a_second_roi(corpus)
        reviewed = ReviewedNames.empty()
        reviewed.record(
            _planted_roi_name(corpus), ReviewedName(Review.MAP, MAPPED_NAME)
        )
        yield _run(corpus, request.param, reviewed)
    else:
        yield _run(corpus, request.param)


@pytest.fixture(name="unreviewed_run", scope="module")
def fixture_unreviewed_run(published):  # pylint: disable = unused-argument
    yield _run(
        _with_a_second_roi(corpus_module.build_corpus()),
        CLEAN_DESCRIPTORS,
        ReviewedNames.empty(),
    )


def _run(corpus, preset, reviewed=None):
    """Run a preset over the corpus, and return what the tests read."""
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        cleaning = (
            None if reviewed is None else DescriptorCleaning(VOCABULARY, reviewed)
        )
        transform = InstanceTransform(
            compose_policy(preset), KEY, cleaning=cleaning, unvalidated_policy=True
        )
        # Only the run's own records and warnings, not those of the tests.
        shown = _Shown()
        logger = logging.getLogger("pydicom")
        logger.addHandler(shown)
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = run.run(
                    run.discover(directory / corpus_module.INSTANCES_DIRECTORY),
                    directory / "release",
                    transform,
                    ReleaseGate(),
                    qc_destination=directory / "qc",
                    reporter=transform.reporter,
                    written_check=transform.written_check,
                )
        finally:
            logger.removeHandler(shown)
        shown_messages = _Messages(
            tuple(shown.messages), tuple(str(warning.message) for warning in caught)
        )
        # The method digest as D-024 composes it, independently of the
        # transform's own.
        digest = method_digest(
            compose_policy(preset),
            vocabulary=None if cleaning is None else cleaning.nomenclature,
            reviewed_roi_names=None if reviewed is None else reviewed.keyed_digest(KEY),
        )
        return _Run(
            preset,
            corpus,
            result,
            _released(result),
            shown_messages,
            _published(result),
            digest,
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _structure_set(corpus):
    (file,) = [file for file in corpus.files if file.manifest.iod == "RT Structure Set"]
    return file


def _planted_roi_name(corpus):
    (placement,) = [
        placement
        for placement in _structure_set(corpus).manifest.placements
        if placement.path.tag == ROI_NAME
    ]
    return placement.values[0]


def _with_a_second_roi(corpus):
    """Return the corpus with a second ROI, named for the automatic tier.

    pydicom writes the structure set again, which keeps every planted value.
    """
    structure_set = _structure_set(corpus)
    dataset = _read(structure_set.data)
    first = dataset.StructureSetROISequence[0]
    item = pydicom.Dataset()
    item.ROINumber = max(each.ROINumber for each in dataset.StructureSetROISequence) + 1
    item.ReferencedFrameOfReferenceUID = first.ReferencedFrameOfReferenceUID
    item.ROIName = UNCLEANED_NAME
    item.ROIGenerationAlgorithm = "MANUAL"
    dataset.StructureSetROISequence.append(item)
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    data = buffer.getvalue()
    return dataclasses.replace(
        corpus,
        files=tuple(
            dataclasses.replace(file, data=data) if file is structure_set else file
            for file in corpus.files
        ),
    )


@dataclasses.dataclass(frozen=True)
class _Run:
    """A preset's run over the corpus, as the tests read it."""

    preset: str
    corpus: corpus_module.SyntheticCorpus
    result: run.RunResult
    released: dict
    messages: "_Messages"
    published: dict
    method_digest: str


@dataclasses.dataclass(frozen=True)
class _Messages:
    logged: tuple[str, ...]
    warned: tuple[str, ...]


class _Shown(logging.Handler):
    """Keep the messages of the log records a run lets out."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _released(result):
    """Return the released files' bytes by run position."""
    return {
        outcome.position: (result.release / outcome.output).read_bytes()
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    }


def _published(result):
    """Return the bytes of every file in the release directory, by its path."""
    return {
        path.relative_to(result.release).as_posix(): path.read_bytes()
        for path in sorted(result.release.rglob("*"))
        if path.is_file()
    }


def _forms(placement):
    """Return each form of a placement's values that is searched for as bytes."""
    forms = set()
    for value in placement.values:
        forms.add(value)
        if placement.vr in ("DA", "DT"):
            forms.add(value[:DATE_DIGITS])
        if placement.vr == "PN":
            # Each component group and component, which a preset could keep
            # on its own.
            forms.update(
                component
                for group in value.split("=")
                for component in (group, *group.split("^"))
            )
    return sorted(form for form in forms if len(form) >= SHORTEST_FORM)


def _searched(placement):
    """Return whether a placement's values are searched for as bytes."""
    return placement.kind in REMOVED_KINDS and (
        placement.vr not in NUMERIC_VRS or placement.vr in NUMBERS_AS_TEXT
    )


def _encodings(form):
    return {
        form.encode("latin-1", errors="ignore"),
        form.encode("utf-8"),
        form.encode("utf-16-le"),
    }


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03", "PS3.15-E.1.1-09")
def test_each_preset_releases_all_but_the_instances_it_must_hold(
    preset_run,
):
    corpus, result = preset_run.corpus, preset_run.result
    names = [file.name for file in corpus.files]
    sequestered = names.index(corpus_module.SEQUESTERED_FILE)
    review = names.index(corpus_module.REVIEW_FILE)

    assert not result.findings
    # What was written refers to itself as the corpus did, but for the
    # references to the instances that were withheld, which are reported.
    assert result.written_findings
    assert all(
        finding.kind is UNWRITTEN_TARGET
        and all(
            position not in (sequestered, review) for (position,) in finding.instances
        )
        for finding in result.written_findings
    )
    assert result.staging_removed
    assert sorted(outcome.position for outcome in result.outcomes) == list(
        range(len(names))
    )
    for outcome in result.outcomes:
        if outcome.position == sequestered:
            assert outcome.status is run.Status.SEQUESTERED
            assert {
                (reason.path.tag, reason.reason)
                for reason in outcome.reasons
                if isinstance(reason, Sequestration)
            } == {
                ("(0010,2297)", SequesterReason.REQUIRED_BY_IOD),
                ("(0010,2299)", SequesterReason.REQUIRED_BY_IOD),
            }
        elif outcome.position == review:
            # The plan's RT Plan Label, found in the dose's Manufacturer's
            # Model Name.
            assert outcome.status is run.Status.HELD_FOR_REVIEW
            assert {
                (reason.decision, reason.code, reason.path)
                for reason in outcome.reasons
                if isinstance(reason, ReleaseReason)
            } == {
                (
                    Decision.QC_REVIEW,
                    ReasonCode.RESIDUAL_TEXT,
                    ElementPath((), "(300A,0002)"),
                )
            }
        else:
            assert outcome.status is run.Status.RELEASED, (
                names[outcome.position],
                outcome.reasons[:5],
            )


@pytest.mark.deid_requirement(
    "MIDI-BP-01",
    "PS3.15-E.1.1-01",
    "PS3.15-E.1.1-04",
    "PS3.15-E.1.1-06",
    "PS3.15-E.1.1-09",
    "PS3.15-E.3.10-02",
    "MIDI-BP-05",
    "MIDI-BP-11",
    "MIDI-BP-13",
)
def test_no_published_file_holds_a_marker(preset_run):
    corpus, result = preset_run.corpus, preset_run.result
    released, published = preset_run.released, preset_run.published
    # The released instances, the release report in both its forms, and the
    # conformance statement, and nothing else.
    assert set(published) == {
        *(
            outcome.output.as_posix()
            for outcome in result.outcomes
            if outcome.position in released
        ),
        RELEASE_REPORT,
        RELEASE_REPORT_MARKDOWN,
        CONFORMANCE_STATEMENT,
    }

    for name, data in published.items():
        for signature in MARKER_SIGNATURES:
            for encoded in _encodings(signature):
                assert encoded not in data, (name, signature)
    # Every file's markers, the sequestered file's included, in every
    # published file.
    for file in corpus.files:
        for placement in file.manifest.placements:
            if not _searched(placement):
                continue
            forms = _forms(placement)
            assert forms, (file.name, placement.path)
            for form in forms:
                for name, data in published.items():
                    for encoded in _encodings(form):
                        assert encoded not in data, (name, file.name, placement.path)


@pytest.mark.deid_requirement("MIDI-BP-14", "PS3.15-E.1.1-02")
def test_released_images_keep_their_transfer_syntax_and_pixels(preset_run):
    corpus, released = preset_run.corpus, preset_run.released
    text = compressed.CODESTREAM_TEXT.encode("ascii")
    images = cut = 0

    for position, data in released.items():
        file = corpus.files[position]
        source, dataset = _read(file.data), _read(data)
        assert dataset.file_meta.TransferSyntaxUID == file.manifest.transfer_syntax
        if "PixelData" not in source:
            continue
        images += 1
        assert (dataset.pixel_array == source.pixel_array).all(), file.name
        if text in file.data:
            # Cut from the codestreams, which were not recompressed.
            assert text not in data
            cut += 1
    assert images
    if (
        preset_run.corpus.files[0].manifest.transfer_syntax
        in compressed.CORPUS_SYNTAXES
    ):
        assert cut


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_numeric_marker_at_its_place(preset_run):
    corpus, released = preset_run.corpus, preset_run.released
    assert released

    for position, data in released.items():
        file = corpus.files[position]
        source = _read(file.data)
        dataset = _read(data)
        for placement in file.manifest.placements:
            if placement.kind not in REMOVED_KINDS or placement.vr not in NUMERIC_VRS:
                continue
            planted = _numbers(placement.vr, placement.values)
            # The comparison can find the marker where it was planted.
            assert _values_at(source, placement.path) == planted, placement.path
            assert _values_at(dataset, placement.path) != planted, (
                file.name,
                placement.path,
            )


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_removed_sequence_without_a_marker(preset_run):
    """A sequence whose item holds no marker is checked by its absence."""
    corpus, released = preset_run.corpus, preset_run.released
    actions = {
        row.tag: row.basic_profile for row in standard.load_table_e1_1().attributes
    }
    checked = 0

    for position, data in released.items():
        file = corpus.files[position]
        dataset = _read(data)
        for placement in file.manifest.placements:
            if (
                placement.reason is corpus_module.NotPlantedReason.NO_MARKER_CARRIER
                and actions[placement.profile_tag] == "X"
            ):
                assert _element_at(_read(file.data), placement.path) is not None
                assert _element_at(dataset, placement.path) is None, (
                    file.name,
                    placement.path,
                )
                checked += 1
    assert checked


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_no_warning_or_log_record_shows_a_marker(preset_run):
    corpus, messages = preset_run.corpus, preset_run.messages
    # pydicom warns about the invalid Device UID, quoting it.
    (invalid,) = [
        placement
        for file in corpus.files
        for placement in file.manifest.placements
        if placement.kind is Kind.INVALID
    ]
    # Both channels are watched.
    assert messages.logged
    assert messages.warned

    for message in (*messages.logged, *messages.warned):
        assert invalid.values[0] not in message
        for signature in MARKER_SIGNATURES:
            assert signature not in message


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.3.5-01")
def test_every_released_instance_claims_the_presets_options(preset_run):
    released = preset_run.released
    clean_descriptors = preset_run.preset == CLEAN_DESCRIPTORS
    assert released

    for data in released.values():
        codes = _codes(_read(data))
        assert BASIC_PROFILE_CODE in codes
        assert (CLEAN_DESCRIPTORS_CODE in codes) == clean_descriptors


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.2-01")
def test_every_released_instance_carries_the_profiles_markers(preset_run):
    # E.1.1: Patient Identity Removed is YES and De-identification Method
    # holds the method digest first; E.2: without the Retain Longitudinal
    # Temporal Information Options, the dates and times are removed.
    released = preset_run.released
    assert released

    for data in released.values():
        dataset = _read(data)
        assert dataset.PatientIdentityRemoved == "YES"
        assert list(_multi(dataset.DeidentificationMethod))[:1] == [
            preset_run.method_digest
        ]
        assert dataset.LongitudinalTemporalInformationModified == "REMOVED"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_roi_names_take_the_vocabulary_spelling_or_the_reviewed_decision(
    preset_run,
):
    corpus, result, released = (
        preset_run.corpus,
        preset_run.result,
        preset_run.released,
    )
    position = corpus.files.index(_structure_set(corpus))
    (outcome,) = [o for o in result.outcomes if o.position == position]
    assert outcome.status is run.Status.RELEASED

    names = [item.ROIName for item in _read(released[position]).StructureSetROISequence]

    if preset_run.preset == CLEAN_DESCRIPTORS:
        assert names == [MAPPED_NAME, VOCABULARY_NAME]
    else:
        assert names == [""]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_without_a_reviewed_decision_the_structure_set_is_held(unreviewed_run):
    corpus, result = unreviewed_run.corpus, unreviewed_run.result
    released, published = unreviewed_run.released, unreviewed_run.published
    position = corpus.files.index(_structure_set(corpus))
    held = [o for o in result.outcomes if o.status is run.Status.HELD_FOR_REVIEW]
    (outcome,) = [o for o in held if o.position == position]

    assert position not in released
    assert {r for r in outcome.reasons if isinstance(r, HeldRoiName)} == {
        HeldRoiName(ElementPath(((ROI_SEQUENCE, 0),), ROI_NAME), Reason.UNMATCHED)
    }
    # The rest are released or held as under a reviewed list.
    assert len(released) == len(corpus.files) - 3
    marker = _planted_roi_name(corpus)
    for data in published.values():
        for encoded in _encodings(marker):
            assert encoded not in data
    for data in released.values():
        assert CLEAN_DESCRIPTORS_CODE in _codes(_read(data))


def _codes(dataset):
    # An item may hold a Long or URN Code Value instead.
    return [
        (item.get("CodeValue"), item.get("CodingSchemeDesignator"))
        for item in dataset.DeidentificationMethodCodeSequence
    ]


def _multi(value):
    return list(value) if isinstance(value, pydicom.multival.MultiValue) else [value]


def _numbers(vr, values):
    """Return values of a numeric VR in a form that compares across writing."""
    if vr in ("AS", "AT"):
        return [str(value).upper() for value in values]
    return [float(value) for value in values]


def _read(data):
    return pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))


def _element_at(dataset, path):
    """Return the element at an element path, or None."""
    for tag, index in path.items:
        number = int(tag[1:5] + tag[6:10], 16)
        if number not in dataset or len(dataset[number].value) <= index:
            return None
        dataset = dataset[number].value[index]
    number = int(path.tag[1:5] + path.tag[6:10], 16)
    return dataset[number] if number in dataset else None


def _values_at(dataset, path):
    """Return the values at an element path, comparable with _numbers, or None."""
    element = _element_at(dataset, path)
    if element is None:
        return None
    value = element.value
    values = list(value) if isinstance(value, pydicom.multival.MultiValue) else [value]
    if element.VR == "AT":
        return [f"{int(each):08X}" for each in values]
    if element.VR == "AS":
        return [str(each).upper() for each in values]
    try:
        return [float(each) for each in values]
    except (TypeError, ValueError):
        return None
