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

"""Each policy run end to end over the synthetic corpus, searched for its markers.

The corpus (:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) plants a
conspicuous marker in each attribute of Table E.1-1 that its IODs define.
Each policy of :data:`~pymedphys.tests.dicom.corpus_runs.CORPUS_RUNS`, a
preset or a custom option set, runs once over it, with what that run must
do. Under the Basic Profile every marker is removed or replaced, so no
released file may hold any of them; an option keeps the markers in the rows
of Table E.1-1 to which it gives K, at their place and nowhere else. The
search here is independent of the engine's own residual search: it looks
for each recorded value as bytes, a value of digits and full stops alone,
such as a date, a decimal, or a UID, only where no digit or full stop is
before it, so that the digits of a replacement UID do not match it by
chance, and checks numeric values, which cannot be searched for, at their
place.

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
none of those markers. That run is skipped where a decoding plugin of those
syntaxes is not installed, as with the ``dicom`` extra alone, which installs
neither GDCM nor pylibjpeg-openjpeg; the engine then sequesters the images as
``no-decoder``, which the instance transform tests cover.
"""

# Each policy's run and its checks share the corpus and its helpers, so they
# stay in one module.
# pylint: disable = too-many-lines

import dataclasses
import io
import json
import logging
import re
import shutil
import struct
import tempfile
import warnings
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    dummy_values,
    pixel_cleaning,
    run,
    standard,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import PRESETS
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldRoiName,
    PixelDataReason,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._dicom.deidentify.run_report import (
    CONFORMANCE_STATEMENT,
    RELEASE_REPORT,
    RELEASE_REPORT_MARKDOWN,
)
from pymedphys._dicom.deidentify.written_references import WrittenFindingKind

from . import _corpus_run as runs
from . import _synthetic_compressed as compressed
from ._corpus_run import (
    CLEAN_DESCRIPTORS,
    KEY,
    MARKER_SIGNATURES,
    ROI_NAME,
    ROI_SEQUENCE,
    CorpusRun,
    planted_roi_name,
    structure_set,
    with_a_second_roi,
)
from .corpus_runs import CORPUS_RUNS

pytestmark = pytest.mark.pydicom

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
# A form of digits and full stops alone, such as a date, a decimal, or a
# UID, could match by chance within the digits of a replacement UID, so it
# is found only where no digit or full stop is before it.
DIGITS_ONLY = re.compile(r"[0-9.]+")
# A SHA-256 in hexadecimal, as the release report gives each engine file's,
# whose digits could hold a date's by chance, as 12071010edb6 holds
# 12071010.
SHA256_HEX = re.compile(rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
DATE_DIGITS = 8
# A file holds an encoded form only if it holds the form's first GRAM bytes,
# so a set of each run of GRAM bytes in a file rules out most forms without
# scanning the file for each.
GRAM = 4
CLEAN_DESCRIPTORS_CODE = ("113105", "DCM")
PERFORMED_PROCEDURE_STEP_SEQUENCE = "(0008,1111)"
IMAGE_COMMENTS = "(0020,4000)"
SOP_INSTANCE_UID = "(0008,0018)"
MEDIA_STORAGE_UID = "(0002,0003)"


def _unreviewed_corpus(corpus):
    return with_a_second_roi(_ct_and_rt(corpus))


def _no_reviewed_names(corpus):  # pylint: disable = unused-argument
    return ReviewedNames.empty()


# Clean Descriptors without a reviewer's decision on the planted ROI Name.
UNREVIEWED = CorpusRun(
    "unreviewed",
    preset=CLEAN_DESCRIPTORS,
    corpus=_unreviewed_corpus,
    reviewed_roi_names=_no_reviewed_names,
)


@pytest.fixture(name="published", scope="module")
def fixture_published():
    with runs.published_vocabulary():
        yield


@pytest.fixture(
    name="policy_run",
    scope="module",
    params=[corpus_run.param() for corpus_run in CORPUS_RUNS],
)
def fixture_policy_run(request, published):  # pylint: disable = unused-argument
    yield _run(request.param)


@pytest.fixture(name="unreviewed_run", scope="module")
def fixture_unreviewed_run(published):  # pylint: disable = unused-argument
    yield _run(UNREVIEWED)


def _ct_and_rt(corpus):
    """Return the corpus's CT Image and RT instances, with its structure set.

    The residual search of each output looks for the values of every
    instance of its patient, so a run's time grows with the square of the
    number of instances; the other instances are run in ``policy_run``.
    """
    return dataclasses.replace(
        corpus,
        files=tuple(
            file
            for file in corpus.files
            if file.manifest.iod
            in ("CT Image", "RT Structure Set", "RT Plan", "RT Dose")
        ),
    )


def _run(spec):
    """Run a policy over its corpus, and return what the tests read."""
    prepared = runs.prepare(spec)
    corpus, reviewed = prepared.corpus, prepared.reviewed
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        transform = prepared.transform(spec.policy())
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
        cleaning = prepared.cleaning
        digest = method_digest(
            spec.policy(),
            vocabulary=None if cleaning is None else cleaning.nomenclature,
            reviewed_roi_names=None if reviewed is None else reviewed.keyed_digest(KEY),
            reviewed_descriptors=(
                None
                if cleaning is None
                else cleaning.reviewed_descriptors.keyed_digest(KEY)
            ),
            technique_vocabulary=(
                None
                if cleaning is None or cleaning.technique is None
                else cleaning.technique.sha256
            ),
            text_finder=(
                None
                if spec.finder is None
                else pixel_cleaning.finder_description(spec.finder)
            ),
        )
        return _Run(
            spec,
            corpus,
            result,
            _released(result),
            shown_messages,
            _published(result),
            digest,
            *_redaction_review(directory / "qc"),
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@dataclasses.dataclass(frozen=True)
class _Run:
    """A policy's run over the corpus, as the tests read it."""

    spec: CorpusRun
    corpus: corpus_module.SyntheticCorpus
    result: run.RunResult
    released: dict
    messages: "_Messages"
    published: dict
    method_digest: str
    qc_pack: dict
    # The size of each redaction preview, as (columns, rows), by its file.
    redaction_previews: dict


def _redaction_review(qc):
    """Return the run's QC pack, and the size of each redaction preview."""
    pack = json.loads((qc / "qc-pack.json").read_text(encoding="ascii"))
    sizes = {}
    for preview in pack["previews"]:
        if preview["kind"] == "redaction":
            header = (qc / preview["file"]).read_bytes()[16:24]
            sizes[preview["file"]] = struct.unpack(">II", header)
    return pack, sizes


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


def _grams(data):
    """Return each run of :data:`GRAM` bytes in a file's bytes."""
    return frozenset(data[i : i + GRAM] for i in range(len(data) - GRAM + 1))


def _within(encoded, data, grams):
    """Return whether ``encoded`` is in ``data``, whose runs are ``grams``."""
    return (len(encoded) < GRAM or encoded[:GRAM] in grams) and encoded in data


def _holds(data, grams, form):
    """Return whether a file's bytes hold a form of a placement's values."""
    if DIGITS_ONLY.fullmatch(form):
        encoded = form.encode("ascii")
        # The search for the bytes alone is the quicker, and rarely finds them.
        if _within(encoded, data, grams) and re.search(
            rb"(?<![0-9.])" + re.escape(encoded), data
        ):
            return True
        return _within(form.encode("utf-16-le"), data, grams)
    return any(_within(encoded, data, grams) for encoded in _encodings(form))


def _instances(result, released):
    """Return the position of each released instance, by its published path."""
    return {
        outcome.output.as_posix(): outcome.position
        for outcome in result.outcomes
        if outcome.position in released
    }


def _markers_in(spec, corpus, instances, published):
    """Return where the published files hold a marker that they may not.

    A released instance may hold the markers that the run keeps at their
    place, which are blanked, once for each place that holds one, before the
    instance is searched like every other published file.
    """
    searched = [
        (file.name, placement.path, _forms(placement))
        for file in corpus.files
        for placement in file.manifest.placements
        if _searched(placement)
    ]
    for file_name, path, forms in searched:
        assert forms, (file_name, path)
    found = []
    for name, data in published.items():
        if name in instances:
            data = _without_kept(data, corpus.files[instances[name]], spec)
        else:
            data = SHA256_HEX.sub(lambda digest: b"-" * 64, data)
        grams = _grams(data)
        found.extend(
            (name, signature)
            for signature in MARKER_SIGNATURES
            if any(_within(encoded, data, grams) for encoded in _encodings(signature))
        )
        found.extend(
            (name, file_name, path)
            for file_name, path, forms in searched
            if any(_holds(data, grams, form) for form in forms)
        )
    return found


def _without_kept(data, file, spec):
    """Return an instance's bytes with each marker kept at its place blanked."""
    dataset, raw = _read(data), _read(data)
    kept = [
        placement.path
        for placement in file.manifest.placements
        if _searched(placement)
        and spec.keeps(placement)
        and _kept_at(dataset, placement)
    ]
    values = [_raw_value_at(raw, path) for path in kept]
    # PS3.10 7.1: Media Storage SOP Instance UID is the SOP Instance UID.
    if ElementPath((), SOP_INSTANCE_UID) in kept:
        values.append(_raw_value_at(raw.file_meta, ElementPath((), MEDIA_STORAGE_UID)))
    for value in sorted(values, key=len, reverse=True):
        assert value in data, (file.name, value)
        data = data.replace(value, b"\0" * len(value), 1)
    return data


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03", "PS3.15-E.1.1-09")
def test_each_run_releases_all_but_the_instances_it_must_withhold(policy_run):
    spec, corpus, result = policy_run.spec, policy_run.corpus, policy_run.result
    names = [file.name for file in corpus.files]
    assert set(spec.withheld) <= set(names)
    withheld = {names.index(name) for name in spec.withheld}

    assert not result.findings
    # What was written refers to itself as the corpus did, but for the
    # references to the instances that were withheld, which are reported.
    assert bool(result.written_findings) == bool(withheld)
    assert all(
        finding.kind is UNWRITTEN_TARGET
        and all(position not in withheld for (position,) in finding.instances)
        for finding in result.written_findings
    )
    assert result.staging_removed
    assert sorted(outcome.position for outcome in result.outcomes) == list(
        range(len(names))
    )
    for outcome in result.outcomes:
        name = names[outcome.position]
        if name in spec.withheld:
            expected = spec.withheld[name]
            assert outcome.status is expected.status, name
            assert {runs.reason_key(r) for r in outcome.reasons} == expected.reasons
        else:
            assert outcome.status is run.Status.RELEASED, (name, outcome.reasons[:5])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_each_cleaned_image_is_listed_and_previewed_frame_by_frame(policy_run):
    spec, corpus, pack = policy_run.spec, policy_run.corpus, policy_run.qc_pack
    blacked_out = HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT)
    cleaned = [
        outcome.position
        for outcome in policy_run.result.outcomes
        if blacked_out in outcome.reasons
    ]
    assert [entry["position"] for entry in pack["redactions"]] == cleaned
    # A run given a review applies the reviewed regions and holds nothing.
    assert bool(cleaned) == (spec.finder is not None and spec.redaction_review is None)
    # Every cleaned image is previewed, whatever its IOD and layout.
    assert not {entry["position"] for entry in pack["not_previewed"]} & set(cleaned)
    previews = [entry for entry in pack["previews"] if entry["kind"] == "redaction"]
    shown = [
        (frame["position"], frame["frame"])
        for entry in previews
        for frame in entry["frames"]
    ]
    assert shown == [
        (entry["position"], frame)
        for entry in pack["redactions"]
        for frame in range(entry["frames"])
    ]
    sizes = iter(policy_run.redaction_previews[entry["file"]] for entry in previews)
    for entry in pack["redactions"]:
        data = corpus.files[entry["position"]].data
        source = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        assert entry["frames"] == int(source.get("NumberOfFrames") or 1)
        regions = {region["frame"]: region["boxes"] for region in entry["regions"]}
        rows, columns = source.Rows, source.Columns
        assert (entry["rows"], entry["columns"]) == (rows, columns)
        # A monochrome frame is shown again over its full range.
        panels = 1 if source.SamplesPerPixel == 3 else 2
        frames = pydicom.pixels.iter_pixels(io.BytesIO(data), raw=True)
        for index, frame in enumerate(frames):
            # Each box is clipped to the frame.
            found = [
                [box.top, box.left, min(box.bottom, rows), min(box.right, columns)]
                for box in spec.finder.find(np.asarray(frame))
            ]
            assert regions.get(index, []) == found
            # A frame with regions is shown beside its source, each panel
            # with a gutter after the first.
            across = panels + 1 if found else panels
            assert next(sizes) == (columns * across + 8 * (across - 1), rows)


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
def test_no_published_file_holds_a_marker(policy_run):
    corpus, result = policy_run.corpus, policy_run.result
    released, published = policy_run.released, policy_run.published
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

    # Every file's markers, the sequestered file's included, in every
    # published file, but for those that a released instance keeps at their
    # place.
    assert not _markers_in(
        policy_run.spec, corpus, _instances(result, released), published
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_a_kept_marker_anywhere_but_its_place_is_found(policy_run):
    """The marker search lets a kept marker be at its place, and nowhere else.

    One released instance has a removed marker put back at its place. A run
    that keeps that row too passes the search; a copy of the marker in the
    release report, or in another attribute of the instance, does not.
    """
    spec, corpus = policy_run.spec, policy_run.corpus
    instances = _instances(policy_run.result, policy_run.released)
    name, position = min(instances.items())
    placement = next(
        placement
        for placement in corpus.files[position].manifest.placements
        if placement.kind is Kind.PLANTED
        and not placement.path.items
        and placement.path.tag != IMAGE_COMMENTS
        and placement.vr in ("LO", "SH")
        and not spec.keeps(placement)
    )
    keeping = dataclasses.replace(spec, kept=spec.kept_rows() | {placement.profile_tag})
    (value,) = placement.values
    dataset = _read(policy_run.released[position])
    dataset.add_new(_number(placement.path.tag), placement.vr, value)
    published = {**policy_run.published, name: _written(dataset)}

    assert _markers_in(spec, corpus, instances, published)
    assert not _markers_in(keeping, corpus, instances, published)
    report = published[RELEASE_REPORT_MARKDOWN] + value.encode("ascii")
    assert _markers_in(
        keeping, corpus, instances, {**published, RELEASE_REPORT_MARKDOWN: report}
    )
    dataset.add_new(_number(IMAGE_COMMENTS), "LT", value)
    assert _markers_in(
        keeping, corpus, instances, {**published, name: _written(dataset)}
    )


@pytest.mark.deid_requirement("MIDI-BP-14", "PS3.15-E.1.1-02")
def test_released_images_keep_their_transfer_syntax_and_pixels(policy_run):
    corpus, released = policy_run.corpus, policy_run.released
    text = compressed.CODESTREAM_TEXT.encode("ascii")
    images = cut = 0

    for position, data in released.items():
        file = corpus.files[position]
        source, dataset = _read(file.data), _read(data)
        assert dataset.file_meta.TransferSyntaxUID == file.manifest.transfer_syntax
        if "PixelData" not in source:
            continue
        images += 1
        pixels, expected = dataset.pixel_array, source.pixel_array
        if policy_run.spec.redaction_review is not None:
            # Each frame's reviewed corner holds one value, its fill.
            frames = int(source.get("NumberOfFrames") or 1)
            rgb = source.get("SamplesPerPixel", 1) > 1
            shape = (frames, *pixels.shape[-3 if rgb else -2 :])
            pixels, expected = pixels.reshape(shape), expected.reshape(shape).copy()
            corner = (
                slice(None),
                slice(0, runs.CORNER.bottom),
                slice(0, runs.CORNER.right),
            )
            corners = pixels[corner].reshape(frames, -1)
            assert (corners == corners[:, :1]).all(), file.name
            expected[corner] = pixels[corner]
        assert (pixels == expected).all(), file.name
        if text in file.data:
            # Cut from the codestreams, which were not recompressed.
            assert text not in data
            cut += 1
    # Clean Pixel Data holds every image that it cleans for review (D-037).
    assert images or "clean_pixel_data" in policy_run.spec.selected
    if (
        policy_run.corpus.files[0].manifest.transfer_syntax
        in compressed.CORPUS_SYNTAXES
    ):
        assert cut


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_numeric_marker_at_its_place(policy_run):
    corpus, released = policy_run.corpus, policy_run.released
    assert released

    for position, data in released.items():
        file = corpus.files[position]
        source = _read(file.data)
        dataset = _read(data)
        for placement in file.manifest.placements:
            if (
                placement.kind not in REMOVED_KINDS
                or placement.vr not in NUMERIC_VRS
                or policy_run.spec.keeps(placement)
            ):
                continue
            planted = _numbers(placement.vr, placement.values)
            # The comparison can find the marker where it was planted.
            assert _values_at(source, placement.path) == planted, placement.path
            assert _values_at(dataset, placement.path) != planted, (
                file.name,
                placement.path,
            )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_each_kept_marker_is_kept_at_its_place(policy_run):
    """An option that gives a row K keeps its marker; the Basic Profile keeps none.

    A marker within a sequence that is not kept goes with the sequence: one
    of Table E.1-1 that an option does not keep (``CorpusRun.keeps``), or a
    Type 3 sequence that a removed attribute it requires takes with it.
    """
    corpus, released = policy_run.corpus, policy_run.released
    kept = []
    assert released

    for position, data in released.items():
        file = corpus.files[position]
        dataset = _read(data)
        for placement in file.manifest.placements:
            if placement.kind not in REMOVED_KINDS or not policy_run.spec.keeps(
                placement
            ):
                continue
            if (
                not placement.path.items
                or _item_at(dataset, placement.path) is not None
            ):
                assert _kept_at(dataset, placement), (file.name, placement.path)
                kept.append(placement)
    if not policy_run.spec.kept_rows():
        assert not kept
    elif any(
        policy_run.spec.keeps(placement)
        for position in released
        for placement in corpus.files[position].manifest.placements
        if placement.kind in REMOVED_KINDS
    ):
        assert kept


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_removed_sequence_without_a_marker(policy_run):
    """A sequence whose item holds no marker is checked by its absence."""
    corpus, released = policy_run.corpus, policy_run.released
    removed = runs.removed_rows(policy_run.spec.selected)
    checked = 0

    for position, data in released.items():
        file = corpus.files[position]
        dataset = _read(data)
        for placement in file.manifest.placements:
            if (
                placement.reason is corpus_module.NotPlantedReason.NO_MARKER_CARRIER
                and placement.profile_tag in removed
            ):
                assert _element_at(_read(file.data), placement.path) is not None
                assert _element_at(dataset, placement.path) is None, (
                    file.name,
                    placement.path,
                )
                checked += 1
    assert checked


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_no_warning_or_log_record_shows_a_marker(policy_run):
    corpus, messages = policy_run.corpus, policy_run.messages
    # pydicom warns about the invalid Device UID, quoting it.
    (invalid,) = [
        placement
        for file in corpus.files
        for placement in file.manifest.placements
        if placement.kind is Kind.INVALID
    ]
    # Both channels are watched, where the value is not kept.
    if not policy_run.spec.keeps(invalid):
        assert messages.logged
        assert messages.warned

    for message in (*messages.logged, *messages.warned):
        assert invalid.values[0] not in message
        for signature in MARKER_SIGNATURES:
            assert signature not in message


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.3.5-01")
def test_every_released_instance_claims_the_policys_options(policy_run):
    corpus, released = policy_run.corpus, policy_run.released
    expected = policy_run.spec.method_codes()
    assert released

    for position, data in released.items():
        source = _read(corpus.files[position].data)
        codes = set(_codes(_read(data)))
        # The profile's and each option's, after any already present.
        assert codes >= expected
        if "DeidentificationMethodCodeSequence" in source:
            assert codes - expected <= set(_codes(source))
        else:
            assert codes == expected


@pytest.mark.deid_requirement("PS3.15-E.3.2-02")
def test_recognizable_visual_features_is_no_exactly_where_the_option_is_claimed(
    policy_run,
):
    corpus, released = policy_run.corpus, policy_run.released
    claimed = "clean_recognizable_visual_features" in policy_run.spec.selected
    assert released

    for position, data in released.items():
        source = _read(corpus.files[position].data)
        written = _read(data).get("RecognizableVisualFeatures")
        if claimed:
            # In every IOD, whether or not it defines the attribute.
            assert written == "NO", corpus.files[position].manifest.iod
        else:
            assert written == source.get("RecognizableVisualFeatures")


@pytest.mark.deid_requirement("PS3.15-E.3.1-02")
def test_burned_in_annotation_is_no_exactly_where_the_option_is_claimed(policy_run):
    corpus, released = policy_run.corpus, policy_run.released
    claimed = "clean_pixel_data" in policy_run.spec.selected
    assert released

    for position, data in released.items():
        source = _read(corpus.files[position].data)
        written = _read(data).get("BurnedInAnnotation")
        if claimed:
            # In every IOD, whether or not it defines the attribute.
            assert written == "NO", corpus.files[position].manifest.iod
        else:
            assert written == source.get("BurnedInAnnotation")


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.2-01")
def test_every_released_instance_carries_the_profiles_markers(policy_run):
    # E.1.1: Patient Identity Removed is YES and De-identification Method
    # holds the method digest first; E.2 and E.3.6: the dates and times are
    # removed without the Retain Longitudinal Temporal Information Options,
    # and otherwise kept or modified.
    released = policy_run.released
    assert released

    for data in released.values():
        dataset = _read(data)
        assert dataset.PatientIdentityRemoved == "YES"
        assert list(_multi(dataset.DeidentificationMethod))[:1] == [
            policy_run.method_digest
        ]
        assert dataset.LongitudinalTemporalInformationModified == (
            policy_run.spec.temporal_value()
        )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01", "MIDI-BP-14")
def test_the_multi_frame_instances_keep_their_reviewed_dummy_values(policy_run):
    # Referenced Performed Procedure Step Sequence, which the multi-frame
    # IODs conditionally require (Type 1C), refers to the procedure step by its keyed replacement,
    # the same in each instance, and the colour image's ICC Profile is the
    # fixed sRGB profile (D-021).
    corpus, released = policy_run.corpus, policy_run.released
    procedure_step = "ReferencedPerformedProcedureStepSequence"
    multi_frame = {
        "Enhanced CT Image",
        "Legacy Converted Enhanced CT Image",
        "Enhanced MR Image",
        "Enhanced MR Color Image",
        "Legacy Converted Enhanced MR Image",
        "MR Spectroscopy",
        "Enhanced PET Image",
        "Legacy Converted Enhanced PET Image",
    }
    steps = set()
    # Under Retain UIDs, Table E.1-1 gives K to the sequence and to the
    # Referenced SOP Instance UID in its item, so each instance keeps the
    # source's sequence in place of the dummy value (PS3.15 E.3.9).
    kept = PERFORMED_PROCEDURE_STEP_SEQUENCE in policy_run.spec.kept_rows()

    for position, data in released.items():
        file = corpus.files[position]
        source, written = _read(file.data), _read(data)
        if kept:
            assert written.get(procedure_step) == source.get(procedure_step)
        if file.manifest.iod not in multi_frame:
            assert kept or procedure_step not in written, file.name
            continue
        assert procedure_step in source
        if not kept:
            (item,) = written[procedure_step].value
            assert item.ReferencedSOPClassUID == (
                corpus_module.MODALITY_PERFORMED_PROCEDURE_STEP
            )
            steps.add(item.ReferencedSOPInstanceUID)
        if file.manifest.iod == "Enhanced MR Color Image":
            assert written.ICCProfile == dummy_values.icc_profile_for_d(
                source.ICCProfile
            )
            assert written.ICCProfile != source.ICCProfile
        else:
            assert "ICCProfile" not in written

    expected = multi_frame & {
        file.manifest.iod
        for file in corpus.files
        if file.name not in policy_run.spec.withheld
    }
    assert {corpus.files[position].manifest.iod for position in released} >= expected
    assert len(steps) == (1 if expected and not kept else 0)
    assert corpus_module.PROCEDURE_STEP not in steps


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_roi_names_take_the_vocabulary_spelling_or_the_reviewed_decision(
    policy_run,
):
    corpus, result, released = (
        policy_run.corpus,
        policy_run.result,
        policy_run.released,
    )
    expected = policy_run.spec.roi_names
    position = corpus.files.index(structure_set(corpus))
    (outcome,) = [o for o in result.outcomes if o.position == position]
    if expected is None:
        assert outcome.status is not run.Status.RELEASED
        return
    assert outcome.status is run.Status.RELEASED

    names = [item.ROIName for item in _read(released[position]).StructureSetROISequence]

    assert names == list(expected)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_without_a_reviewed_decision_the_structure_set_is_held(unreviewed_run):
    corpus, result = unreviewed_run.corpus, unreviewed_run.result
    released, published = unreviewed_run.released, unreviewed_run.published
    position = corpus.files.index(structure_set(corpus))
    held = [o for o in result.outcomes if o.status is run.Status.HELD_FOR_REVIEW]
    (outcome,) = [o for o in held if o.position == position]

    assert position not in released
    assert {r for r in outcome.reasons if isinstance(r, HeldRoiName)} == {
        HeldRoiName(ElementPath(((ROI_SEQUENCE, 0),), ROI_NAME), Reason.UNMATCHED)
    }
    # The rest are released or held as under a reviewed list.
    assert len(released) == len(corpus.files) - 3
    marker = planted_roi_name(corpus)
    for data in published.values():
        for encoded in _encodings(marker):
            assert encoded not in data
    for data in released.values():
        assert CLEAN_DESCRIPTORS_CODE in _codes(_read(data))


def test_the_kept_rows_are_those_table_e1_1_gives_k():
    # Device Serial Number is K under Retain Device Identity, but Station AE
    # Title is C; Date of Last Calibration is K under Retain Device Identity
    # and C under Modified Dates, which tps-import applies.
    device = runs.kept_rows(("retain_device_identity",))
    tps_import = runs.kept_rows(PRESETS["tps-import"])

    assert not runs.kept_rows(())
    assert not runs.kept_rows(PRESETS["basic-clean-descriptors"])
    assert {"(0018,1000)", "(0008,1010)", "(0018,1200)"} <= device
    assert "(0008,0055)" not in device
    assert "(0018,1000)" in tps_import
    assert "(0018,1200)" not in tps_import
    assert runs.kept_rows(("retain_uids",)) >= {"(0018,1002)", "(0020,000D)"}


def test_each_option_of_table_e1_1_has_its_code_and_temporal_value():
    assert set(runs.OPTION_CODES) == set(standard.OPTIONS)
    assert runs.temporal_value(()) == "REMOVED"
    assert runs.temporal_value((runs.MODIFIED_DATES,)) == "MODIFIED"
    assert runs.temporal_value((runs.FULL_DATES,)) == "UNMODIFIED"


def test_each_run_names_a_policy_once():
    names = [corpus_run.name for corpus_run in CORPUS_RUNS]

    assert len(set(names)) == len(names)
    for corpus_run in CORPUS_RUNS:
        assert corpus_run.policy().options == corpus_run.selected
    with pytest.raises(ValueError, match="not both"):
        CorpusRun("both", preset="basic", options=("clean_descriptors",))
    with pytest.raises(TypeError):
        CorpusRun("one string", options="clean_descriptors")
    with pytest.raises(ValueError, match="needs Clean Structured Content"):
        CorpusRun(
            "no option",
            options=("retain_uids",),
            kept_content=frozenset({"(0040,0555)"}),
        )
    with pytest.raises(ValueError, match="no sequence of content items"):
        CorpusRun(
            "not content items",
            options=("clean_structured_content",),
            kept_content=frozenset({ROI_SEQUENCE}),
        )


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


def _written(dataset):
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer)
    return buffer.getvalue()


def _kept_at(dataset, placement):
    """Return whether a dataset holds a placement's values at its place."""
    if placement.vr in NUMERIC_VRS:
        planted = _numbers(placement.vr, placement.values)
        return _values_at(dataset, placement.path) == planted
    element = _element_at(dataset, placement.path)
    if element is None:
        return False
    value = element.value
    if isinstance(value, bytes):
        values = value.decode("latin-1").split("\\")
    elif isinstance(value, pydicom.multival.MultiValue):
        values = [str(each) for each in value]
    else:
        values = [str(value)]
    return [each.rstrip(" \x00") for each in values] == [
        each.rstrip(" \x00") for each in placement.values
    ]


def _item_at(dataset, path):
    """Return the item that holds the element at an element path, or None.

    A sequence that pydicom's dictionary does not know reads back as UN,
    whose value holds the items in Implicit VR Little Endian (PS3.5 6.2.2).
    """
    for tag, index in path.items:
        number = _number(tag)
        if number not in dataset:
            return None
        items = dataset[number].value
        if isinstance(items, bytes):
            items = pydicom.values.convert_SQ(items, True, True)
        if len(items) <= index:
            return None
        dataset = items[index]
    return dataset


def _raw_value_at(dataset, path):
    """Return the bytes of an element's value as its file holds them."""
    element = _item_at(dataset, path).get_item(_number(path.tag))
    assert isinstance(element.value, bytes), path
    return element.value


def _number(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _element_at(dataset, path):
    """Return the element at an element path, or None."""
    dataset = _item_at(dataset, path)
    if dataset is None:
        return None
    number = _number(path.tag)
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
