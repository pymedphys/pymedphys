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

"""Two runs of the synthetic corpus under one project key (D-004).

Under each preset, the corpus is exported in two runs under one project key
file and its subject profile store. Each run reads the key and opens the
store afresh, as a custodian's separate runs do, and saves the store before
it publishes. The first run exports the corpus's CT slices, structure set,
other images, and registrations. The second exports its plans, doses,
records, and reports, many of which reference the first run's instances,
exports two of the first run's instances again, and exports two studies of
the same subject that the first run did not see: a prior study, 37 days
before the corpus's, and a follow-up, 93 days after it, each a copy of the
corpus's first CT slice with every date moved by its interval and every UID
re-rooted.

Both runs must give the subject one Patient ID and one Patient's Name, and
each source UID one replacement, so that the second run's references
resolve to the instances that the first run wrote; write each value that
both runs receive alike; write an instance that both runs receive byte for
byte alike; and leave the store as the first run saved it. Under the presets
with Modified Dates, both runs must move every subject-event date by one
whole-week offset, so that the other studies keep their intervals to the
corpus's study.

Under ``tps-import`` a later run must also write the birth date that an
earlier one chose and saved in the subject's profile. The corpus's own study
gives no birth date, since each of its instances holds its own Study Date
and Patient's Age, so the follow-up study is exported alone, and then the
prior study alone, which, as the subject's earliest study, would give
another birth date without the store.

Two controls show that the checks can fail. The prior study exported under
another project key has another Patient ID, Patient's Name, offset, and
replacement for every replaced UID. Exported under the same key with a new
store, it has the same pseudonyms, UIDs, and offset, which the key alone
derives, and under ``tps-import`` a birth date of its own, which only the
store prevents.

The checks are independent of the engine's composition of the policy: each
pairs a source element with what the released instance holds at the same
place, so that a value dropped or written with another VR is compared too,
and reads which dates move by the subject's offset from the reviewed
temporal roles alone.
"""

import dataclasses
import datetime
import functools
import hashlib
import io
import json
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    command,
    keys,
    run,
    run_report,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.policy import PRESETS
from pymedphys._dicom.deidentify.temporal_roles import (
    TemporalAction,
    load_temporal_roles,
)

from . import _corpus_run as runs
from ._corpus_run import MODIFIED_DATES, CorpusRun
from .corpus_runs import CORPUS_RUNS

pytestmark = pytest.mark.pydicom

# The project key of both runs, and another, for the control. Fixed, so
# that the controls' differences are the same on every run of the tests.
PROJECT_KEY = keys.DeidKey(bytes(range(64, 96)))
OTHER_KEY = keys.DeidKey(bytes(range(96, 128)))

# The corpus's files, by the number that begins each name, that the first
# run exports: its CT slices, structure set, images, and registrations.
FIRST_RUN_NUMBERS = frozenset({1, 2, 3, 4, *range(8, 20)})
# The first run's instances that the second run exports again.
EXPORTED_AGAIN = ("01-ct-1.dcm", "04-rtstruct.dcm")
# The CT slice that each other study copies.
COPIED_SLICE = "01-ct-1.dcm"
# The Patient's Age, in completed years, that each copy gives, so that
# under tps-import its study gives a birth date; the corpus's own ages are
# markers in weeks, which give none.
AGE = "042Y"
TPS_IMPORT = "tps-import"


@dataclasses.dataclass(frozen=True)
class OtherStudy:
    """A study of the corpus's subject that the first run does not see.

    Attributes
    ----------
    name : str
        What its copies' file names end with.
    days : int
        How many days after the corpus's study it was acquired; negative
        for a prior study. Not a whole number of weeks, so that it cannot
        stand in for the subject's offset.
    """

    name: str
    days: int

    @property
    def file_name(self) -> str:
        """The file name of its copy of :data:`COPIED_SLICE`."""
        return f"{Path(COPIED_SLICE).stem}-{self.name}.dcm"


PRIOR = OtherStudy("prior", -37)
FOLLOW_UP = OtherStudy("follow-up", 93)
OTHER_STUDIES = (PRIOR, FOLLOW_UP)

PATIENT_ID = pydicom.tag.Tag(0x0010, 0x0020)
PATIENT_NAME = pydicom.tag.Tag(0x0010, 0x0010)
PATIENT_BIRTH_DATE = pydicom.tag.Tag(0x0010, 0x0030)
STUDY_DATE = pydicom.tag.Tag(0x0008, 0x0020)
SOP_INSTANCE_UID = pydicom.tag.Tag(0x0008, 0x0018)
# UIDs that the standard defines, such as SOP Classes and transfer syntaxes,
# which no run replaces and no copy re-roots.
STANDARD_UID_ROOT = "1.2.840.10008."
# The root of every replacement UID that a run derives from its key (D-003).
KEYED_UID_ROOT = "2.25."
# Values of these VRs are bytes or binary numbers, which no pseudonym or
# replacement UID takes.
BINARY_VRS = frozenset(
    {"AT", "FD", "FL", "OB", "OD", "OF", "OL", "OV", "OW", "SL", "SS", "SV"}
    | {"UL", "UN", "US", "UV", "US or SS", "OB or OW", "US or OW", "US or SS or OW"}
)
_DATE = "%Y%m%d"


def _number(name: str) -> int:
    return int(name.partition("-")[0])


# Place: each sequence above the element as (tag, item index), then the tag;
# the file meta information's elements under the tag (0002,0000).
Place = tuple
FILE_META = pydicom.tag.Tag(0x0002, 0x0000)


def _elements(
    dataset: pydicom.Dataset, above: tuple = ()
) -> Iterator[tuple[Place, pydicom.DataElement]]:
    """Yield each element of the data set, at every level, with its place."""
    for element in dataset:
        if element.VR == "SQ":
            for index, item in enumerate(element.value):
                yield from _elements(item, (*above, (element.tag, index)))
        else:
            yield (*above, element.tag), element


def _text_values(data: bytes) -> dict[Place, tuple[str, str]]:
    """Return each text value of an instance, as (VR, value), by its place.

    A value of several values is joined with backslashes, as it is encoded.
    """
    dataset = pydicom.dcmread(io.BytesIO(data))
    found = {}
    meta = [((FILE_META, element.tag), element) for element in dataset.file_meta]
    for place, element in (*meta, *_elements(dataset)):
        if element.VR in BINARY_VRS or element.value is None:
            continue
        value = element.value
        if isinstance(value, bytes):
            continue
        if isinstance(value, pydicom.multival.MultiValue):
            text = "\\".join(str(each) for each in value)
        else:
            text = str(value)
        found[place] = (element.VR, text)
    return found


def _shape(place: Place) -> tuple:
    """A place without its item indices, so that items of a sequence share it."""
    return tuple(each[0] if isinstance(each, tuple) else each for each in place)


@dataclasses.dataclass(frozen=True)
class Export:
    """One run under a project key, as the tests read it.

    Attributes
    ----------
    sources : Mapping of str to bytes
        Each input, by its file name in the corpus.
    released : Mapping of str to bytes
        Each released instance, by its input's file name.
    report : dict
        The release report.
    store : bytes
        The subject profile store as the run left it, or nothing where the
        run saved none.
    """

    sources: Mapping[str, bytes]
    released: Mapping[str, bytes]
    report: dict
    store: bytes

    def outcomes(self) -> Iterator[tuple[str, Place, str, str, tuple[str, str] | None]]:
        """Yield each source text value of a released instance with what was written.

        Each as (file name, place, VR, source value, written), where written
        is the released element at the same place as (VR, value), or None
        where the released instance holds none there, so that a value that
        a run drops, or writes with another VR, is compared too.
        """
        for name, data in self.released.items():
            released = _text_values(data)
            for place, (vr, received) in _text_values(self.sources[name]).items():
                yield name, place, vr, received, released.get(place)

    def pairs(self) -> Iterator[tuple[str, Place, str, str, str]]:
        """Yield each released text value with the source value at its place.

        Each as (file name, place, VR, source value, released value), where
        the released instance holds an element of the same VR at the same
        place as the source.
        """
        for name, place, vr, received, written in self.outcomes():
            if written is not None and written[0] == vr:
                yield name, place, vr, received, written[1]

    def top_level(self, tag) -> set[str]:
        """The values of a top-level attribute across the released instances."""
        return {
            str(pydicom.dcmread(io.BytesIO(data))[tag].value)
            for data in self.released.values()
            if tag in pydicom.dcmread(io.BytesIO(data))
        }

    def uids(self) -> dict[str, set[str]]:
        """Each source UID's replacements in the released instances."""
        found: dict[str, set[str]] = {}
        for _, place, vr, received, written in self.pairs():
            if vr == "UI":
                for each, replacement in _components(place, received, written):
                    found.setdefault(each, set()).add(replacement)
        return found

    def offsets(self) -> set[int]:
        """How many days each subject-event date moved back, as a set.

        Each DA value of an attribute whose reviewed temporal role moves it
        by the subject's offset, paired with the source date at its place,
        but Patient's Birth Date, which Modified Dates leaves to its Basic
        Profile action and ``tps-import`` synthesises. A source date that
        is written empty fails, since such a date moves and is never
        emptied.
        """
        rules = _temporal_rules()
        found = set()
        for _, place, vr, received, written in self.pairs():
            tag = place[-1]
            rule = rules.get(f"({tag.group:04X},{tag.element:04X})")
            if (
                vr != "DA"
                or tag == PATIENT_BIRTH_DATE
                or rule is None
                or rule.role.action is not TemporalAction.SHIFT
            ):
                continue
            for before, after in _components(place, received, written):
                if before:
                    assert after, place
                    found.add((_parse(before) - _parse(after)).days)
        return found


def _components(place: Place, received: str, written: str) -> zip:
    """Pair the values of a source element with those written in its place.

    The value multiplicity must be kept, so that no value of either goes
    unpaired.
    """
    before, after = received.split("\\"), written.split("\\")
    assert len(before) == len(after), place
    return zip(before, after, strict=True)


@functools.cache
def _temporal_rules():
    return load_temporal_roles().rules


def _parse(value: str) -> datetime.date:
    return datetime.datetime.strptime(value, _DATE).date()


def _moved(value: str, days: int) -> str:
    """Move a DA value, or a DT value's date, by ``days``, if it is one."""
    try:
        date = _parse(value[:8])
    except ValueError:
        return value
    return (date + datetime.timedelta(days=days)).strftime(_DATE) + value[8:]


def _re_rooted(uid: str, study: OtherStudy) -> str:
    """Return a UID of the other study in place of the corpus's ``uid``.

    Under 2.25 from a digest of the study and the UID, so each copy's
    references stay consistent and no UID of the corpus recurs.
    """
    if not uid or uid.startswith(STANDARD_UID_ROOT):
        return uid
    digest = hashlib.sha256(f"{study.name}\0{uid}".encode()).digest()
    return f"2.25.{int.from_bytes(digest[:16], 'big')}"


def _copy(
    file: corpus_module.CorpusFile, study: OtherStudy
) -> corpus_module.CorpusFile:
    """Return a copy of a CT slice as an instance of the other study.

    Every DA value but Patient's Birth Date, and the date of every DT value,
    moves by the study's interval, every UID that the standard does not
    define is re-rooted, and Patient's Age is :data:`AGE`. Every other
    value, the subject's identity among them, is kept.
    """
    dataset = pydicom.dcmread(io.BytesIO(file.data))
    for place, element in _elements(dataset):
        if element.VR == "UI":
            values = (
                list(element.value)
                if isinstance(element.value, pydicom.multival.MultiValue)
                else [element.value]
            )
            moved = [_re_rooted(str(each), study) for each in values]
            element.value = moved if len(moved) > 1 else moved[0]
        elif element.VR in ("DA", "DT") and place != (PATIENT_BIRTH_DATE,):
            if isinstance(element.value, pydicom.multival.MultiValue):
                element.value = [
                    _moved(str(each), study.days) for each in element.value
                ]
            elif element.value:
                element.value = _moved(str(element.value), study.days)
    dataset.PatientAge = AGE
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    manifest = dataclasses.replace(
        file.manifest,
        name=study.file_name,
        sop_instance=str(dataset.SOPInstanceUID),
    )
    return corpus_module.CorpusFile(manifest, buffer.getvalue())


def _with_other_studies(spec: CorpusRun) -> CorpusRun:
    """The run's corpus with the other studies' copies of its CT slice.

    So that a face or redaction review of the corpus covers the copies too.
    """

    def corpus(received):
        received = spec.corpus(received)
        (copied,) = [file for file in received.files if file.name == COPIED_SLICE]
        copies = tuple(_copy(copied, study) for study in OTHER_STUDIES)
        return dataclasses.replace(received, files=(*received.files, *copies))

    return dataclasses.replace(spec, corpus=corpus)


def _export(
    spec: CorpusRun,
    prepared: runs.Prepared,
    names: frozenset[str],
    key_file: Path,
    store: Path,
    directory: Path,
) -> Export:
    """Run the policy over the named files under a project key and its store.

    The key file is read and the store opened afresh, as a custodian's new
    run does, and the store is saved before the release is published.
    """
    files = tuple(file for file in prepared.corpus.files if file.name in names)
    assert {file.name for file in files} == names
    directory.mkdir()
    corpus_module.write_corpus(
        dataclasses.replace(prepared.corpus, files=files), directory
    )
    source = directory / corpus_module.INSTANCES_DIRECTORY
    release = directory / "release"
    qc = directory / "qc"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(keys, "PROJECT_KEYS_ENABLED", True)
        key, profiles = command.run_key(
            key_file, store, source=source, release=release, qc_pack=qc
        )
    assert profiles is not None and profiles.persistent
    transform = prepared.transform(spec.policy(), key=key, profiles=profiles)
    discovery = run.discover(source)
    result = run.run(
        discovery,
        release,
        transform,
        ReleaseGate(),
        qc_destination=qc,
        reporter=transform.reporter,
        written_check=transform.written_check,
        before_publish=command.profile_saver(profiles),
    )
    released = {
        discovery.paths[outcome.position].name: (
            result.release / outcome.output
        ).read_bytes()
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    }
    # Each run withholds what the policy's corpus run withholds, and
    # releases every other file it is given, so no split loses coverage.
    assert set(released) == names - set(spec.withheld)
    return Export(
        sources={file.name: file.data for file in files},
        released=released,
        report=json.loads(
            (result.release / run_report.RELEASE_REPORT).read_text(encoding="utf-8")
        ),
        store=store.read_bytes() if store.exists() else b"",
    )


@dataclasses.dataclass(frozen=True)
class Exports:
    """A policy's two runs under one project key, and the controls."""

    spec: CorpusRun
    first: Export
    second: Export
    # The prior study under another project key, and under the same key
    # with a new store.
    other_key: Export
    new_store: Export
    # The store as the first run saved it.
    first_store: bytes
    # Under tps-import, the follow-up study alone, then the prior study
    # alone under the same key and store, and the prior study alone with a
    # new store; None under another preset.
    birth_dates: tuple[Export, Export, Export] | None = None

    @property
    def both(self) -> tuple[Export, Export]:
        return (self.first, self.second)


@functools.cache
def _exports(name: str) -> Exports:
    """Export the corpus in two runs under one project key, and the controls."""
    spec = _with_other_studies({each.name: each for each in CORPUS_RUNS}[name])
    with runs.published_vocabulary():
        prepared = runs.prepare(spec)
        names = frozenset(file.name for file in prepared.corpus.files)
        copies = frozenset(study.file_name for study in OTHER_STUDIES)
        first = frozenset(
            name for name in names - copies if _number(name) in FIRST_RUN_NUMBERS
        )
        prior = frozenset({PRIOR.file_name})
        second = (names - first) | frozenset(EXPORTED_AGAIN)
        # A short directory, since a run refuses output paths that could
        # exceed Windows' 259 characters.
        directory = Path(tempfile.mkdtemp(prefix="k"))
        try:
            custodian = directory / "c"
            custodian.mkdir()
            key_file = keys.write_key_file(custodian / "key.json", PROJECT_KEY)
            other_key_file = keys.write_key_file(custodian / "other.json", OTHER_KEY)
            store = custodian / "profiles.json"
            first_export = _export(
                spec, prepared, first, key_file, store, directory / "1"
            )
            first_store = first_export.store
            second_export = _export(
                spec, prepared, second, key_file, store, directory / "2"
            )
            other_key = _export(
                spec,
                prepared,
                prior,
                other_key_file,
                custodian / "other-profiles.json",
                directory / "o",
            )
            new_store = _export(
                spec, prepared, prior, key_file, custodian / "new.json", directory / "n"
            )
            birth_dates = None
            if spec.preset == TPS_IMPORT:
                # The corpus's own study holds a different Study Date and
                # Patient's Age in each instance, so no birth date can be
                # chosen in a run that holds it; the other studies alone can.
                store = custodian / "birth-dates.json"
                birth_dates = (
                    _export(
                        spec,
                        prepared,
                        frozenset({FOLLOW_UP.file_name}),
                        key_file,
                        store,
                        directory / "b1",
                    ),
                    _export(spec, prepared, prior, key_file, store, directory / "b2"),
                    _export(
                        spec,
                        prepared,
                        prior,
                        key_file,
                        custodian / "birth-dates-new.json",
                        directory / "b3",
                    ),
                )
        finally:
            shutil.rmtree(directory, ignore_errors=True)
    return Exports(
        spec,
        first_export,
        second_export,
        other_key,
        new_store,
        first_store,
        birth_dates,
    )


# Each preset's own run, by its name; not the basic preset's run over the
# compressed corpus, whose keyed values are those of the basic run.
PRESET_RUNS = tuple(each for each in CORPUS_RUNS if each.name == each.preset)
DATED_RUNS = tuple(each for each in PRESET_RUNS if MODIFIED_DATES in each.selected)


@pytest.fixture(
    name="exports", scope="module", params=[each.param() for each in PRESET_RUNS]
)
def fixture_exports(request) -> Exports:
    return _exports(request.param.name)


@pytest.fixture(
    name="dated", scope="module", params=[each.param() for each in DATED_RUNS]
)
def fixture_dated(request) -> Exports:
    return _exports(request.param.name)


def test_every_preset_is_exported_in_two_runs():
    assert sorted(each.preset for each in PRESET_RUNS) == sorted(PRESETS)
    assert {each.preset for each in DATED_RUNS} == {
        preset for preset, options in PRESETS.items() if MODIFIED_DATES in options
    }


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.1.3-01")
def test_both_runs_are_under_the_project_key(exports):
    for export in exports.both:
        assert export.report["key"] == {
            "scope": "project",
            "key_id": PROJECT_KEY.key_id,
        }
    assert exports.other_key.report["key"]["key_id"] == OTHER_KEY.key_id


@pytest.mark.deid_requirement("MIDI-BP-12")
def test_the_second_run_leaves_the_store_as_the_first_saved_it(exports):
    document = json.loads(exports.first_store)
    assert document["key_id"] == PROJECT_KEY.key_id
    # A subject's profile is recorded where a value is read from it: its
    # date offset under Modified Dates, which tps-import's birth date also
    # takes.
    dated = MODIFIED_DATES in exports.spec.selected
    assert len(document["subjects"]) == (1 if dated else 0)
    assert exports.second.store == exports.first_store


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.1.3-01")
def test_an_instance_exported_again_is_written_alike(exports):
    for name in EXPORTED_AGAIN:
        assert name in exports.first.released
        assert exports.second.released[name] == exports.first.released[name]


def _released_names(export: Export, study: OtherStudy) -> bool:
    return study.file_name in export.released


@pytest.mark.deid_requirement("MIDI-BP-12")
def test_both_runs_give_the_subject_one_patient_id_and_name(exports):
    first, second = exports.both
    # Each study's instances are exported, the other studies' in the
    # second run.
    assert all(_released_names(second, study) for study in OTHER_STUDIES)
    for tag in (PATIENT_ID, PATIENT_NAME):
        # The corpus gives each instance its own Patient's Name, a marker,
        # and every instance the subject's one Patient ID.
        received = {
            str(pydicom.dcmread(io.BytesIO(data))[tag].value)
            for export in exports.both
            for data in export.sources.values()
        }
        (written,) = first.top_level(tag) | second.top_level(tag)
        assert written and written not in received
        assert exports.new_store.top_level(tag) == {written}
        (other,) = exports.other_key.top_level(tag)
        assert other != written and other not in received


def _keyed(uid: str, replacement: str) -> bool:
    """Whether a UID was given a replacement derived from the key (D-003)."""
    return replacement != uid and replacement.startswith(KEYED_UID_ROOT)


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.1.3-01")
def test_both_runs_give_each_source_uid_one_replacement(exports):
    first, second = (export.uids() for export in exports.both)
    combined: dict[str, set[str]] = {}
    for found in (first, second):
        for uid, replacements in found.items():
            combined.setdefault(uid, set()).update(replacements)
    for uid, replacements in combined.items():
        assert len(replacements) == 1, uid
    replaced = {
        uid: replacement
        for uid, (replacement,) in combined.items()
        if _keyed(uid, replacement)
    }
    # Different source UIDs are never given one replacement.
    assert len(set(replaced.values())) == len(replaced)
    # The Study Instance UID, the frame of reference, and others reach both.
    assert len(first.keys() & second.keys() & replaced.keys()) >= 3
    # The key alone derives them: a new store gives the same, and another
    # key another for each.
    new_store = exports.new_store.uids()
    other = exports.other_key.uids()
    assert new_store.keys() & replaced.keys()
    for uid in new_store.keys() & replaced.keys():
        assert new_store[uid] == {replaced[uid]}
    assert other.keys() & replaced.keys()
    for uid in other.keys() & replaced.keys():
        assert other[uid] != {replaced[uid]}


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.1.3-01")
def test_the_second_runs_references_resolve_to_the_first_runs_instances(exports):
    first, second = exports.both
    # The SOP Instance UIDs that the first run alone wrote, by their source's.
    written = {}
    for name, data in first.released.items():
        if name not in second.sources:
            received = pydicom.dcmread(io.BytesIO(first.sources[name])).SOPInstanceUID
            written[str(received)] = str(
                pydicom.dcmread(io.BytesIO(data)).SOPInstanceUID
            )
    # The places, by shape, at which some released instance of either run
    # keeps a UID.
    kept = {
        _shape(place)
        for export in exports.both
        for _, place, vr, _, _ in export.pairs()
        if vr == "UI"
    }
    resolved = 0
    for _, place, vr, received, outcome in second.outcomes():
        if vr != "UI" or received not in written:
            continue
        if outcome is None:
            # Dropped only where the policy removes every UID at its place,
            # whichever run holds the instance it names.
            assert _shape(place) not in kept, place
        else:
            assert outcome == ("UI", written[received]), place
            resolved += 1
    assert resolved >= 1


@pytest.mark.deid_requirement("MIDI-BP-12")
def test_each_value_both_runs_receive_is_written_alike(exports):
    """Each source value is written alike wherever either run receives it.

    A value is compared by its instance's SOP Class, since an action
    resolved by Type can differ between IODs, and by the shape of its place,
    so that one instance's value is compared with another's, and its outcome
    includes its VR and whether it was written at all. This covers every
    pseudonym, replacement UID, and modified date, and every other value.
    """
    found: dict[tuple, set] = {}
    received_in: dict[tuple, set[int]] = {}
    for index, export in enumerate(exports.both):
        classes = {
            name: str(pydicom.dcmread(io.BytesIO(data)).SOPClassUID)
            for name, data in export.sources.items()
        }
        for name, place, vr, received, outcome in export.outcomes():
            key = (classes[name], _shape(place), vr, received)
            found.setdefault(key, set()).add(outcome)
            received_in.setdefault(key, set()).add(index)
    assert sum(len(each) == 2 for each in received_in.values()) >= 1000
    for key, outcomes in found.items():
        assert len(outcomes) == 1, key[1:3]


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.3.6-02")
def test_both_runs_move_the_subjects_dates_by_one_offset(dated):
    (offset,) = dated.first.offsets() | dated.second.offsets()
    assert offset % 7 == 0
    assert 52 <= offset // 7 <= 520
    # The key alone derives it: a new store gives the same, and another key
    # another.
    assert dated.new_store.offsets() == {offset}
    (other,) = dated.other_key.offsets()
    assert other != offset


def _study_date(export: Export, name: str) -> datetime.date:
    return _parse(str(pydicom.dcmread(io.BytesIO(export.released[name])).StudyDate))


@pytest.mark.deid_requirement("MIDI-BP-12", "PS3.15-E.3.6-02")
def test_the_other_studies_keep_their_intervals(dated):
    first, second = dated.both
    reference = _study_date(first, COPIED_SLICE)
    for study in OTHER_STUDIES:
        moved = _study_date(second, study.file_name)
        assert (moved - reference).days == study.days


@pytest.mark.deid_requirement("MIDI-BP-12")
def test_a_later_run_keeps_the_subjects_birth_date():
    exports = _exports(TPS_IMPORT)
    assert exports.birth_dates is not None
    follow_up, prior, new_store = exports.birth_dates
    (chosen,) = follow_up.top_level(PATIENT_BIRTH_DATE)
    assert chosen
    # The prior study, now the subject's earliest, takes the follow-up's
    # choice, which the store kept.
    assert prior.top_level(PATIENT_BIRTH_DATE) == {chosen}
    assert prior.store == follow_up.store
    # Without the store, the prior study gives another.
    (own,) = new_store.top_level(PATIENT_BIRTH_DATE)
    assert own and own != chosen
