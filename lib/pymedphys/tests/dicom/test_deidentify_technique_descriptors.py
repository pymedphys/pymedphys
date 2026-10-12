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
"""The automatic tier of free-text Clean Descriptors, and the common names.

Every descriptor value here is synthetic.
"""

import copy
import io
import json
import tarfile
import tomllib

from pymedphys._imports import pytest

from pymedphys._dev import deid_common_names as generator
from pymedphys._dicom.deidentify import common_names
from pymedphys._dicom.deidentify import technique_descriptors as technique
from pymedphys._dicom.deidentify.residual_exemptions import defined_terms
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    Held,
    Outcome,
    ReviewedDescriptor,
    ReviewedDescriptors,
    clean_descriptor_values,
    descriptor_attributes,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review
from pymedphys._dicom.deidentify.technique_descriptors import Rejection

SERIES_DESCRIPTION = "(0008,103E)"
PROTOCOL_NAME = "(0018,1030)"
STUDY_DESCRIPTION = "(0008,1030)"
IMAGE_COMMENTS = "(0020,4000)"


@pytest.fixture(name="vocabulary", scope="module")
def fixture_vocabulary():
    return technique.load_technique_vocabulary()


@pytest.fixture(name="document")
def fixture_document():
    return tomllib.loads(technique.VOCABULARY_FILE.read_text(encoding="utf-8"))


def _read(document):
    return technique.read_vocabulary(
        document,
        names=common_names.load_common_names(),
        terms=defined_terms(),
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "value",
    [
        "AX T1 POST GAD",
        "CT CHEST W CONTRAST",
        "t2_tse_tra_320",
        "Ax DWI B1000",
        "ep2d_diff_3scan_trace_p2",
        "SAG T2 FLAIR 3D",
        "Thorax 1.0 B70f",
        "Head 5.0 H30s",
        "PET WB CTAC 3D",
        "AC CT 3.75mm",
        "Abd/Pel Delayed",
        "MPRAGE iso 1mm",
        "Soft Tissue 3mm",
        "Recon 2: Lung",
        "HEAD STANDARD",
        "FATSAT",
        "WINDOW1",
        "localizer",
        "Topogram 0.6 T20s",
        "DE_Abdomen_ME 1.5 Q30f",
        "t2_spc_sag_p2_iso",
        "t2_tirm_tra_dark-fluid",
        "3D Brain VIEW FLAIR",
        "AX T2 3T",
    ],
)
def test_technique_values_made_of_vocabulary_words_are_kept(vocabulary, value):
    assert vocabulary.rejection(SERIES_DESCRIPTION, value) is None
    assert vocabulary.keeps(PROTOCOL_NAME, value)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "value, rejection",
    [
        ("Smith head", Rejection.NAME),
        ("AX T1 JOHN", Rejection.NAME),
        ("Brown chest", Rejection.NAME),
        ("Paul", Rejection.NAME),
        ("CT HEAD AL45", Rejection.NAME),
        ("CT HEAD MRS HAND", Rejection.NAME),
        ("MR MAX HAND", Rejection.NAME),
        ("AX T1 HU^MA", Rejection.NAME),
        ("Dr Quokka chest", Rejection.UNKNOWN_WORD),
        ("CHEST Wombat", Rejection.UNKNOWN_WORD),
        ("45Y F", Rejection.UNKNOWN_WORD),
        ("CHEST MALE", Rejection.UNKNOWN_WORD),
        ("HEAD MRN", Rejection.UNKNOWN_WORD),
        ("CHEST M45", Rejection.UNKNOWN_WORD),
        ("AX T1 YR45", Rejection.UNKNOWN_WORD),
        ("AX T1 PT12F", Rejection.UNKNOWN_WORD),
        ("AX T1 J45M", Rejection.UNKNOWN_WORD),
        ("CT HEAD 45F", Rejection.UNKNOWN_WORD),
        ("CT HEAD 45 D", Rejection.INITIALS_AGE_OR_SEX),
        ("CT 6 W", Rejection.INITIALS_AGE_OR_SEX),
        ("CT HEAD BY C L", Rejection.INITIALS_AGE_OR_SEX),
        ("AX T1 C.L.", Rejection.INITIALS_AGE_OR_SEX),
        ("T1 2026-10-12", Rejection.DATE_OR_TIME),
        ("T1 12/10/26", Rejection.DATE_OR_TIME),
        ("AX T1 12_10_26", Rejection.DATE_OR_TIME),
        ("CT 12;10;26", Rejection.DATE_OR_TIME),
        ("CT HEAD 12/10", Rejection.NUMBER),
        ("CT 14:30", Rejection.DATE_OR_TIME),
        ("CT HEAD 14.30", Rejection.DATE_OR_TIME),
        ("CT 14H30", Rejection.NUMBER),
        ("HEAD 12345", Rejection.NUMBER),
        ("CT 1234 5678", Rejection.NUMBER),
        ("CT HEAD 1234_5678", Rejection.NUMBER),
        ("CT 1234X5678", Rejection.NUMBER),
        ("CT 12-345", Rejection.NUMBER),
        ("T12 345", Rejection.NUMBER),
        ("CT HEAD 1430", Rejection.NUMBER),
        ("AX T1 1998", Rejection.NUMBER),
        ("SERIES2026", Rejection.NUMBER),
        ("CT HEAD 1210.2026", Rejection.NUMBER),
        ("CT HEAD 0412.345.678", Rejection.NUMBER),
        ("CT HEAD 1 1 26", Rejection.DATE_OR_TIME),
        ("CT CHEST\u00e9", Rejection.NOT_PRINTABLE),
        ("CT\tCHEST", Rejection.NOT_PRINTABLE),
        ("3 5", Rejection.NUMBER),
        ("B70f", Rejection.NO_VOCABULARY_WORD),
    ],
)
def test_values_with_names_dates_numbers_or_other_words_are_not_kept(
    vocabulary, value, rejection
):
    assert vocabulary.rejection(SERIES_DESCRIPTION, value) is rejection


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize("tag", [STUDY_DESCRIPTION, IMAGE_COMMENTS, "(0008,1080)"])
def test_study_description_comments_and_diagnoses_are_never_kept_automatically(
    vocabulary, tag
):
    assert tag in descriptor_attributes()
    assert vocabulary.rejection(tag, "CT CHEST") is Rejection.NOT_AUTOMATIC


def test_the_automatic_attributes_are_the_planned_technique_descriptors(vocabulary):
    assert vocabulary.attributes == {
        "(0008,103E)",
        "(0018,1030)",
        "(0018,0024)",
        "(0018,0010)",
        "(0018,1040)",
        "(0008,2111)",
        "(0040,0254)",
        "(0028,1055)",
        "(0054,1101)",
        "(0054,1105)",
        "(0054,1103)",
    }
    assert vocabulary.attributes <= set(descriptor_attributes())


def test_the_vocabulary_holds_no_common_name_that_is_not_an_exception(
    vocabulary, document
):
    names = common_names.load_common_names()
    exceptions = set(document["exceptions"])

    assert not (vocabulary.words & names) - exceptions
    assert vocabulary.names == names - exceptions
    assert not vocabulary.words & set(document["excluded"])
    # Terms of PS3.3 and Annex L join the vocabulary, apart from names.
    assert {"CHEST", "ABDOMEN", "HELICAL", "SPIRAL"} <= vocabulary.words
    assert "ANN" in names and "ANN" not in vocabulary.words


def test_compounds_join_two_or_three_words_of_at_least_three_letters(vocabulary):
    assert vocabulary.keeps(SERIES_DESCRIPTION, "AXIALFLAIR")
    assert vocabulary.keeps(SERIES_DESCRIPTION, "CHESTABDOPELVIS")
    assert not vocabulary.keeps(SERIES_DESCRIPTION, "LUNGLIVERBONEBRAIN")
    # WO, MB, and AT are words, but too short to join: short words would
    # spell too many names.
    assert {"WO", "MB", "AT"} <= vocabulary.words
    assert not vocabulary.keeps(SERIES_DESCRIPTION, "WOMBAT")


def test_its_repr_and_digest_hold_no_word(vocabulary, document):
    changed = copy.deepcopy(document)
    changed["group"][0]["words"].append("QUOKKA")

    assert repr(vocabulary).startswith("TechniqueVocabulary(attributes=11, words=")
    assert vocabulary.sha256 == _read(document).sha256
    assert _read(changed).sha256 != vocabulary.sha256
    assert len(vocabulary.sha256) == 64


@pytest.mark.parametrize(
    "change, problem",
    [
        (lambda d: d.update(schema="other"), "is not a"),
        (lambda d: d["attributes"].append("(0010,0010)"), "not descriptors"),
        (lambda d: d["attributes"].append("(0008,103E)"), "repeats a tag"),
        (lambda d: d["term_attributes"].append("(0008,103E)"), "no terms"),
        (lambda d: d["group"][0]["words"].append("JOHN"), "1 common names"),
        (lambda d: d["group"][0]["words"].append("AGE"), "1 excluded words"),
        (lambda d: d["group"][0]["words"].append("ax"), "capital letters"),
        (lambda d: d["group"][0].pop("basis"), "needs a name and a basis"),
        (lambda d: d["exceptions"].update(QUOKKA="A marsupial."), "an exception"),
        (lambda d: d["exceptions"].update(HEAD=""), "needs its basis"),
        (lambda d: d.update(group=[]), "holds no groups"),
        (lambda d: d["kernels"].append("ABC"), "one or two letters"),
        (lambda d: d["kernels"].append("UR"), "1 excluded words"),
    ],
)
def test_an_invalid_vocabulary_is_refused(document, change, problem):
    change(document)

    with pytest.raises(technique.TechniqueVocabularyError, match=problem):
        _read(document)


def test_an_unreadable_vocabulary_file_is_refused(tmp_path):
    path = tmp_path / "vocabulary.toml"
    path.write_text("schema = [", encoding="utf-8")

    with pytest.raises(technique.TechniqueVocabularyError, match="cannot be read"):
        technique.load_technique_vocabulary(path)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_cleaning_keeps_vocabulary_values_and_holds_echoes(vocabulary):
    reviewed = ReviewedDescriptors.empty()

    cleaned = clean_descriptor_values(
        SERIES_DESCRIPTION,
        ["AX T1 POST GAD", "HAND", "Quokka scan", ""],
        reviewed,
        identifiers=["HAND^QUOKKA"],
        vocabulary=vocabulary,
    )

    assert [(c.outcome, c.held_because, c.value) for c in cleaned] == [
        (Outcome.KEPT_BY_VOCABULARY, None, "AX T1 POST GAD"),
        (Outcome.HELD, Held.ECHOES_IDENTIFIER, None),
        (Outcome.HELD, Held.UNREVIEWED, None),
        (Outcome.EMPTY, None, ""),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_reviewers_decision_takes_precedence_over_the_vocabulary(vocabulary):
    reviewed = ReviewedDescriptors.empty()
    reviewed.record(
        SERIES_DESCRIPTION, "AX T1 POST GAD", ReviewedDescriptor(Review.EMPTY)
    )

    without, with_ = (
        clean_descriptor_values(
            SERIES_DESCRIPTION,
            ["AX T1 POST GAD"],
            reviewed,
            identifiers=(),
            vocabulary=each,
        )[0]
        for each in (None, vocabulary)
    )

    assert without.outcome is with_.outcome is Outcome.EMPTIED
    held = clean_descriptor_values(
        STUDY_DESCRIPTION, ["CT CHEST"], reviewed, identifiers=(), vocabulary=vocabulary
    )
    assert held[0].outcome is Outcome.HELD


def test_the_shipped_common_names_load():
    names = common_names.load_common_names()

    assert len(names) > 20_000
    assert {"JOHN", "SMITH", "MARY", "HEAD"} <= names
    assert "QUOKKA" not in names


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    common_names.load_common_names.cache_clear()
    return path


@pytest.mark.parametrize(
    "change, problem",
    [
        (lambda d: d.update(schema="other"), "is not a"),
        (lambda d: d["names"].append("smith"), "is not a"),
        (lambda d: d["names"].insert(0, "ZZZ"), "sorted and distinct"),
        (lambda d: d["names"].pop(), "digest"),
    ],
)
def test_a_changed_common_names_file_is_refused(tmp_path, change, problem):
    document = json.loads(common_names.COMMON_NAMES_FILE.read_text(encoding="utf-8"))
    change(document)
    path = _write(tmp_path / "names.json", document)

    with pytest.raises(common_names.CommonNamesFileError, match=problem):
        common_names.load_common_names(path)


def test_a_common_names_file_that_is_not_an_object_is_refused(tmp_path):
    path = _write(tmp_path / "names.json", [1, 2])

    with pytest.raises(common_names.CommonNamesFileError, match="is not a"):
        common_names.load_common_names(path)


def _source(rows):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for member, text in rows.items():
            content = text.encode("ascii")
            info = tarfile.TarInfo(f"names-0.3.0/{member}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_the_generator_keeps_given_names_and_surnames_above_the_threshold(
    tmp_path, monkeypatch
):
    source = _source(
        {
            "names/dist.male.first": "QUOLL          0.010  0.010      1\n",
            "names/dist.female.first": "BILBY          0.001  0.001      1\n",
            "names/dist.all.last": (
                "WOMBAT         0.002  0.002      1\n"
                "NUMBAT         0.001  0.003      2\n"
                "POTOROO        0.000  0.003      3\n"
            ),
        }
    )
    monkeypatch.setattr(
        generator, "SOURCE_SHA256", generator.hashlib.sha256(source).hexdigest()
    )
    path = tmp_path / "source.tar.gz"
    path.write_bytes(source)
    output = tmp_path / "names.json"

    count = generator.generate(path, output)

    assert count == 4
    assert common_names.load_common_names(output) == {
        "BILBY",
        "NUMBAT",
        "QUOLL",
        "WOMBAT",
    }


def test_the_generator_refuses_a_source_without_the_pinned_digest(tmp_path):
    path = tmp_path / "source.tar.gz"
    path.write_bytes(b"not the pinned source")

    assert generator.main([str(path), "--output", str(tmp_path / "out.json")]) == 1
    assert not (tmp_path / "out.json").exists()
