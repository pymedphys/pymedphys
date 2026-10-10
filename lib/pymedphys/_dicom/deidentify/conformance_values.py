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

"""Write the sections of the conformance statement on what the engine writes.

:func:`~pymedphys._dicom.deidentify.conformance_markdown.render_markdown`
takes four sections of the statement from here, each generated from the
engine's own constants and functions, so that it changes when they do:

- :func:`values_written`: the values that Z, D, and U write, from
  :mod:`~pymedphys._dicom.deidentify.dummy_values`,
  :mod:`~pymedphys._dicom.deidentify.pseudonyms`, and
  :mod:`~pymedphys._dicom.deidentify.uids` (D-003, D-005, and D-021);
- :func:`dates_and_times`: how the policy handles dates and times, by its
  Retain Longitudinal Temporal Information Option or without one (D-006,
  D-007, and D-023);
- :func:`residual_search`: what the search of each written file for the
  source values that were removed or replaced covers, and what it does not
  search, from :mod:`~pymedphys._dicom.deidentify.residuals` (D-027);
- :func:`release_report`: how the release report names sequestered
  instances and counts the values that the residual search does not
  search, from :mod:`~pymedphys._dicom.deidentify.release_report` (D-026
  and D-027).

Each names tags, VRs, actions, and the engine's constants, never a value
from an instance or a key.
"""

from __future__ import annotations

import base64
import types
from collections.abc import Callable, Iterable, Mapping

from . import dummy_values, pixel_risk, pseudonyms, residuals, uids
from . import release_report as report
from .conformance import ConformanceStatement
from .edits import PSEUDONYM_TAGS
from .pixel_risk import Indicator
from .qc_retained import _NOT_REVIEWED_TAGS, RETAINED_TEXT_VRS
from .reasons import TransformReason
from .release_gate import ReasonCode
from .release_report import _HOLDING, _SEQUESTERING
from .reviewed_roi_names import Outcome as RoiNameOutcome
from .residuals import _BINARY as _BINARY_VRS
from .residuals import _KINDS
from .residuals import _NUMBERS as _NUMBER_VRS
from .residuals import _PIXEL_DATA
from .values import CHECKED_VRS
from .walker import REVIEWED_DUMMY_SEQUENCES

TEMPORAL_MODIFIED = "(0028,0303)"  # Longitudinal Temporal Information Modified
_SERIES_INSTANCE_UID = "(0020,000E)"

# The name of each codec in which the residual search encodes every form.
CODEC_NAMES: Mapping[str, str] = types.MappingProxyType(
    {"utf-8": "UTF-8", "latin-1": "ISO 8859-1", "utf-16-le": "UTF-16LE"}
)

# The VRs whose values the residual search searches.
_SEARCHED_VRS = frozenset(_KINDS)


def unsearched_vrs() -> Mapping[residuals.Omission, tuple[str, ...]]:
    """Return the VRs whose values the residual search does not search, by reason.

    A value of a VR other than SQ that the search has no kind for is not
    searched: as binary, or as a code, number, age, time, or tag that occurs
    throughout files.
    """
    others = CHECKED_VRS - _SEARCHED_VRS
    return types.MappingProxyType(
        {
            residuals.Omission.BINARY: tuple(sorted(others & _BINARY_VRS)),
            residuals.Omission.NOT_DISTINCTIVE: tuple(sorted(others - _BINARY_VRS)),
        }
    )


def join(values: Iterable[str], conjunction: str = "and") -> str:
    """Join ``values`` as prose: ``"a"``, ``"a and b"``, or ``"a, b, and c"``."""
    values = list(values)
    if len(values) <= 2:
        return f" {conjunction} ".join(values)
    return ", ".join(values[:-1]) + f", {conjunction} " + values[-1]


def code(action: str) -> str:
    """Return ``action`` as inline code."""
    return f"`{action}`"


# Why a form of a value, or a spelling of it, is not searched.
OMISSIONS: Mapping[residuals.Omission, str] = types.MappingProxyType(
    {
        residuals.Omission.TOO_SHORT: (
            f"Forms of fewer than {residuals.MIN_CHARACTERS} characters, "
            "counted once composed (NFKC)"
        ),
        residuals.Omission.NOT_DISTINCTIVE: (
            "Values of VR "
            + join(unsearched_vrs()[residuals.Omission.NOT_DISTINCTIVE])
            + ", whose codes, numbers, ages, times, and tags occur throughout "
            "files, and datetimes without a full date, such as a year alone"
        ),
        residuals.Omission.BINARY: (
            "Binary values, of VR "
            + join(unsearched_vrs()[residuals.Omission.BINARY], "or")
        ),
        residuals.Omission.CODE_EXTENSIONS: (
            "Spellings of a form in the source's character set with other ISO "
            "2022 escape sequences than its codec writes, such as a writer "
            "puts before each component"
        ),
    }
)


# Why a value is not given to the residual search at all.
UNSEARCHED_REASONS: Mapping[residuals.UnsearchedReason, str] = types.MappingProxyType(
    {
        residuals.UnsearchedReason.RETAINED: (
            "the policy retains the value, so it is dropped from the search"
        ),
        residuals.UnsearchedReason.WRITTEN_CONSTANT: (
            "the value, one of its values, or a form of a value equals, as D "
            "compares values, a constant that the engine writes whatever the "
            "source held; other values and forms are still searched"
        ),
        residuals.UnsearchedReason.UNDECODABLE: (
            "the value could not be decoded to collect it, and is removed or replaced"
        ),
        residuals.UnsearchedReason.REGISTERED_UID: (
            "the value is a UID that the pinned tables register, which names no one"
        ),
    }
)

# What each stage that sequesters an instance does.
STAGES: Mapping[str, str] = types.MappingProxyType(
    {
        "scope": "the instance is outside the supported scope",
        "admission": "its source file was refused and set aside",
        "references": "the first pass's reference graph sequestered it",
        "walker": "an element's action could not be applied at its place",
        "run": (
            "the run's own checks after its first pass refused it, such as for "
            "a source file that changed during the run or an output name that "
            "another instance shares"
        ),
        "transform": (
            "the instance could not be transformed, such as for an edit still "
            "to come when its output is written, or a ROI Name that descriptor "
            "cleaning could not decode"
        ),
        "writer": "its output could not be written as planned",
        "verifier": (
            "the written output could not be shown to preserve each value that "
            "the policy keeps"
        ),
        "release": (
            "the release gate withheld it, for what the residual search found "
            "in its written file, a written file not read to its end, or a "
            "value of it or of another instance of its subject that could not "
            "be collected for the search"
        ),
    }
)

# The codes by which the release gate can hold an instance for review rather
# than withhold it: a gap in collection for a value of no required kind, and
# other text found inside the data set.
REVIEW_CODES = frozenset(
    code.value
    for code in (
        ReasonCode.UNCOLLECTED,
        ReasonCode.NOT_REPORTED,
        ReasonCode.READ_AS_LATIN_1,
        ReasonCode.COLLECTED_AS_OTHER_VR,
        ReasonCode.RESIDUAL_TEXT,
    )
)

# What each stage that holds an instance for review does.
HOLDING_STAGES: Mapping[str, str] = types.MappingProxyType(
    {
        "roi-names": "descriptor cleaning sent one of its ROI Names to review",
        "release": (
            "the release gate requires QC review, for other text that the "
            "residual search found inside the data set, or a value that could "
            "not be collected for the search and is not a person name, UID, "
            "date, datetime, direct identifier, or sequence"
        ),
    }
)


def _reviewed_items(named: Callable[[str], str]) -> list[str]:
    """Describe what D writes where a reviewed rule gives the value (D-021)."""
    lines = []
    for tag, compared in REVIEWED_DUMMY_SEQUENCES.items():
        if tag == dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE:
            lines.append(_procedure_step_items(named, tag, compared))
            continue
        (first,) = dummy_values.items_for_d(tag, [])
        source = {e.tag: e.value for e in first if e.tag in compared}
        (second,) = dummy_values.items_for_d(tag, [source])
        changed = [
            f"{named(element.tag)} `{element.value}`"
            for element, before in zip(second, first)
            if element.value != before.value
        ]
        lines.append(
            f"D on {named(tag)} writes one item, with "
            + join(f"{named(element.tag)} `{element.value}`" for element in first)
            + ". Where a source item's "
            + join((named(t) for t in sorted(compared)), "or")
            + " equals the item's, as D compares values, the item has "
            + join(changed)
            + " instead (D-021)."
        )
    lines.append(_icc_profile(named))
    return lines


def _procedure_step_items(
    named: Callable[[str], str], tag: str, compared: frozenset[str]
) -> str:
    """Describe the items that D writes in Referenced Performed Procedure Step Sequence."""
    (uid,) = compared
    return (
        f"D on {named(tag)} writes, for each source item, one item, with "
        f"{named('(0008,1150)')} "
        f"`{dummy_values.MODALITY_PERFORMED_PROCEDURE_STEP}`, the Modality "
        f"Performed Procedure Step SOP Class, and {named(uid)} the keyed "
        "replacement of the source item's, as D writes for a UI attribute. "
        f"Where the sequence has no item, or an item has no {named(uid)}, "
        "the instance is sequestered (D-021)."
    )


def _icc_profile(named: Callable[[str], str]) -> str:
    """Describe the profile that D writes in place of ICC Profile."""
    first, second = dummy_values.CONSTANTS["LO"]
    return (
        f"D on {named(dummy_values.ICC_PROFILE)} writes a fixed ICC version "
        "2.4 input profile of the sRGB colour space of IEC 61966-2.1, "
        f"described `{first} sRGB`, or `{second} sRGB` where the source has "
        "the same bytes. PS3.3 Section C.11.15.1.1 requires the profile's "
        "data colour space to be RGB, so where the source is not an RGB "
        "profile, the instance is sequestered. Pixel values are preserved, "
        "but the source profile's colorants and tone curves are not, so colour "
        "rendering can change substantially (D-021)."
    )


def _naming_pymedphys(named: Callable[[str], str]) -> list[str]:
    """Name each value that a reviewed rule writes and that names PyMedPhys."""
    return [
        f"{named(element.tag)} `{element.value}`"
        for tag in REVIEWED_DUMMY_SEQUENCES
        # The procedure step's items hold only UIDs, written for the source.
        if tag != dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE
        for item in dummy_values.items_for_d(tag, [])
        for element in item
        if "PYMEDPHYS" in element.value.upper()
    ]


def values_written(named: Callable[[str], str]) -> list[str]:
    """Return the lines of the section on the values that Z, D, and U write.

    ``named`` gives an attribute's name and tag, such as ``"Patient ID
    (0010,0020)"``.
    """
    code_length = len(base64.b32encode(bytes(pseudonyms.CODE_BYTES)).rstrip(b"="))
    patient_id_length = len(pseudonyms.PATIENT_ID_PREFIX) + code_length
    # A replacement UID is the root and the decimal form of a 128-bit UUID.
    uid_length = len(uids.UID_ROOT) + len(str(2**128 - 1))
    exceptions = _naming_pymedphys(named)
    pseudonym_tags = join(named(tag) for tag in sorted(PSEUDONYM_TAGS))
    rows = [
        f"| {vr} | `{first}` | `{second}` |"
        for vr, (first, second) in dummy_values.CONSTANTS.items()
    ]
    return [
        "## Values written",
        "",
        "Z writes a zero-length value, except where this statement says "
        "otherwise. D writes one constant for each VR, valid for that VR, "
        "whatever the source value. Where any source value equals the first "
        "constant, as the VR defines equality, D writes the second, so the "
        "value always changes. It writes the fewest values that the "
        "attribute's VM allows (D-021).",
        "",
        "| VR | Value | Value where the source equals the first |",
        "| --- | --- | --- |",
        *rows,
        "",
        "D on a UI attribute writes the keyed replacement of each source UID. "
        "D on an attribute of any other VR, such as CS or SQ, "
        "needs a reviewed rule for that attribute; without one, the instance "
        "is sequestered (D-021).",
        *(item for line in _reviewed_items(named) for item in ("", line)),
        "",
        f"At the top level of the data set, {pseudonym_tags} take the "
        "subject's keyed pseudonyms wherever Z or D applies to them (D-005); "
        "elsewhere, as in an item of a sequence, Z and D write as above. "
        f"Patient ID takes `{pseudonyms.PATIENT_ID_PREFIX}` followed by the "
        f"subject's code, {patient_id_length} characters in all, and "
        f"Patient's Name takes `{pseudonyms.FAMILY_NAME}^` followed by the "
        f"same code as the given name. The code is the {code_length} "
        "characters of the base32 form (RFC 4648) of the first "
        f"{pseudonyms.CODE_BYTES * 8} bits of the key's `patient` derivation "
        "of the subject's identity: a Patient ID with its "
        f"{named('(0010,0021)')}, or a curated subject identifier.",
        "",
        f"U replaces a UID with `{uids.UID_ROOT}` followed by the decimal form "
        f"of a name-based (version 5) UUID, at most {uid_length} characters "
        f"in all. The UUID's namespace is `{uids.UID_NAMESPACE}`, and its name "
        "is the HMAC-SHA256 of the unpadded source UID under the key (D-003). "
        "A UID that the pinned tables of PS3.6 Annex A and PS3.16 register, "
        "such as a well-known frame of reference, is retained, because it "
        "names a public definition rather than an instance; this interprets "
        "U for such values. A replaced value of a UI attribute of the "
        "definition role is also reported.",
        "",
        "No value that Z, D, or U writes names PyMedPhys"
        + (
            f", except the {join(exceptions)} of the item that D writes in "
            f"{named(dummy_values.PERSON_IDENTIFICATION_CODE_SEQUENCE)}, which "
            "names who defines its code (D-021)."
            if exceptions
            else "."
        ),
    ]


def dates_and_times(
    statement: ConformanceStatement,
    named: Callable[[str], str],
    option: Callable[[str], str],
) -> list[str]:
    """Return the lines of the section on how dates and times are handled.

    ``option`` gives an option's Code Meaning and CID 7050 code.
    """
    temporal = statement.temporal
    actions = {e.tag: e.action for e in statement.attributes}
    counts = join(f"{code(action)} for {count}" for action, count in temporal.actions)
    covered = (
        f"The temporal roles cover {temporal.attributes} attributes: every DA, "
        "DT, and TM attribute of the pinned data dictionary, and "
        + join(named(tag) for tag in temporal.other_attributes)
        + ", which Table E.1-1 cleans under Retain Longitudinal Temporal "
        "Information with Modified Dates. Each takes the action listed under "
        f"Actions: {counts}."
    )
    if temporal.option:
        return [
            "## Dates and times",
            "",
            f"The policy selects {option(temporal.option)}. {covered} How the "
            "attributes that it cleans are modified, by their temporal roles "
            "(D-006 and D-007), is not yet described; see below.",
        ]
    timezone = "(0008,0201)"
    vrs = ("DA", "DT", "TM")
    firsts = join(f"`{dummy_values.CONSTANTS[vr][0]}` for {vr}" for vr in vrs)
    seconds = join(f"`{dummy_values.CONSTANTS[vr][1]}`" for vr in vrs)
    return [
        "## Dates and times",
        "",
        "The policy selects no Retain Longitudinal Temporal Information "
        "Option, so no date or time is shifted or otherwise modified: the "
        "Basic Profile's actions apply (D-006). "
        f"{covered} Those of the attributes that Table E.1-1 omits take their "
        "supplementary rules (D-023), and the temporal roles apply only under "
        "Modified Dates (D-007).",
        "",
        f"D writes, whatever the source value, {firsts}, or, where the source "
        f"equals that value, {seconds} respectively, as Values written gives "
        "them. Z "
        "writes a zero-length value, or D's constant where the attribute is "
        "Type 1 or 1C at its place (D-020). "
        f"{named(timezone)} takes {code(actions[timezone])}, and "
        f"{named(TEMPORAL_MODIFIED)} is "
        f"`{statement.markers.temporal}`, as Attributes inserted describes.",
    ]


def residual_search(named: Callable[[str], str]) -> list[str]:
    """Return the lines of the section on what the residual search covers."""
    codecs = join(CODEC_NAMES[codec] for codec in residuals.CODECS)
    pixel_data = join(named(tag) for tag in sorted(_PIXEL_DATA))
    numbers = join(sorted(_NUMBER_VRS), "or")
    return [
        "## Residual search",
        "",
        "The engine collects each source value that it removes or replaces, "
        "at every level of nesting and with the descendants of a removed "
        "sequence, for the residual search, which searches every byte of a "
        "written file for them before the file is released: the "
        "preamble, the File Meta Information, every element, Data Set "
        "Trailing Padding, and the bytes after the last readable element "
        "(D-027). Values of VR "
        + join(sorted(_SEARCHED_VRS))
        + f" are searched in {codecs}, and in the source's character set, "
        "in several forms of each, such as each name of a person name and "
        "each common spelling of a date, and a longer value by its first "
        f"{residuals.MAX_CHARACTERS} characters. In {pixel_data} of the "
        f"top-level data set, where native, and where a written file holds "
        f"values of VR {numbers}, "
        f"only forms of at least {residuals.MIN_BYTES_IN_NUMBERS} bytes that "
        "are not UTF-16LE are searched, since shorter forms match sample "
        "values by chance. RLE Lossless Pixel Data is searched in the same "
        "way. In the entropy-coded data of other encapsulated Pixel Data of "
        "the top-level data set, only forms of at least "
        f"{residuals.MIN_BYTES_IN_CODED} bytes that are not UTF-16LE are "
        "searched.",
        "",
        "These are not searched, and the search lists each by its source "
        "attribute and reason, never by its value:",
        "",
        *(f"- {OMISSIONS[reason]}." for reason in residuals.Omission),
        "",
        "Each finding names the value's kind, its source attribute, the form "
        "and encoding found, and its place in the file, never the value.",
    ]


def _held_by(stage: str, codes: Iterable[str]) -> list[str]:
    """Return the codes by which a stage can hold an instance for review."""
    if stage == "release":
        return [c for c in codes if c in REVIEW_CODES]
    return list(codes)


# The names under which a run writes its release report, the report's
# human-readable form, and this statement, as ``run_report`` gives them; the
# statement's tests check that they agree. ``run_report`` imports the
# statement, so it is not imported here.
_RELEASE_REPORT = "release-report.json"
_RELEASE_REPORT_MARKDOWN = "release-report.md"
_CONFORMANCE_STATEMENT = "conformance-statement.md"


def qc_pack(named: Callable[[str], str]) -> list[str]:
    """Return the lines of the section on what the QC pack lists for review."""
    vrs = join(sorted(RETAINED_TEXT_VRS), "or")
    exempt = join(named(tag) for tag in sorted(_NOT_REVIEWED_TAGS))
    unreviewable = code(TransformReason.UNREVIEWABLE_RETAINED_TEXT.value)
    volume = join((code(each.value) for each in pixel_risk.VOLUME_INDICATORS), "or")
    head, unreadable = (
        code(indicator.value)
        for indicator in (Indicator.HEAD_OR_NECK, Indicator.UNREADABLE)
    )
    return [
        "## QC pack",
        "",
        "The confidential QC pack of each run lists, for the review of every "
        "distinct retained string, each distinct string that an instance's "
        "plan keeps as it is, in an element of VR "
        f"{vrs} outside any removed sequence, other than {exempt}, with every "
        "place where it was kept (D-017). The run sequesters an instance "
        "with such a value that cannot be decoded for review, such as text "
        "outside ISO 646 where no Specific Character Set applies, by "
        f"{unreviewable}, rather than releasing it unreviewed.",
        "",
        "The engine writes Pixel Data (7FE0,0010) unchanged and claims "
        "neither Clean Pixel Data nor Clean Recognizable Visual Features. "
        "The QC pack lists each instance whose source's attributes show an "
        "indicator of text burned into its pixel data, of a face that could "
        "be reconstructed, or of values that may disclose the patient's body "
        "weight, with those indicators, and, where the "
        "instance is released or held for review, previews its written file "
        "at full resolution or records why it could not. The engine reads "
        "these indicators from the "
        "instance's attributes, never from its pixel data, so the absence "
        "of an indicator is not evidence that the risk is absent (D-015).",
        "",
        "The QC pack also lists each CT, MR, and PET volume among the "
        "instances that are "
        "released or held for review, as one that may hold a face that could "
        f"be reconstructed, by {volume}, whether or not it covers the face, "
        "since the engine cannot tell without inspecting its pixel data; "
        "where the volume's attributes name a region of the head or neck in "
        f"a reviewed list from PS3.16 Annex L, by {head}; and where such "
        f"evidence cannot be read, by {unreadable}; each with the instances "
        "that show it. A volume is a series whose images of one of those "
        "modalities hold at least two frames that are not localizers, or an "
        "Enhanced or Legacy Converted Enhanced image whose Number of Frames "
        "cannot be read. "
        "The run groups instances into series by their source's "
        f"{named(_SERIES_INSTANCE_UID)}, which it never writes, and assesses "
        "only the released and held instances, so a series with just one "
        "single-frame image among them is not a volume (D-015).",
    ]


def release_report() -> list[str]:
    """Return the lines of the section on what the release report records."""
    (first,) = report.sequestration_labels(1)
    stages = [
        f"- {code(stage)}: {STAGES[stage]}, by "
        + join((code(c) for c in sorted(codes)), "or")
        + "."
        for stage, codes in _SEQUESTERING.items()
    ]
    holding = [
        f"- {code(stage)}: {HOLDING_STAGES[stage]}, by "
        + join((code(c) for c in sorted(_held_by(stage, codes))), "or")
        + "."
        for stage, codes in _HOLDING.items()
    ]
    omissions = join((code(o.value) for o in residuals.Omission), "or")
    return [
        "## Release report",
        "",
        "The release report of a run, a JSON document in the format "
        f"`{report.FORMAT}`, names a sequestered instance, which has no "
        f"output name, by a label for the run, from `{first}` to `S-n` for `n` "
        "sequestered instances, assigned in an order drawn at random, so that "
        "a label says nothing of the instance or its place in the run "
        "(D-026). With each label, the report gives each reason that one of "
        "these stages sequestered the instance, as the stage and its reason "
        "code:",
        "",
        *stages,
        "",
        "A reason from the walker also gives the attribute's tags from the "
        "outermost sequence, without items, the action, and the VR where it "
        "is known, and one from the release gate gives the attribute's tags "
        "in the same way where it names an attribute. A reason of scope "
        "`unsupported-iod` also gives the instance's IOD by its name in "
        "PS3.4 Table B.5-1, such as `Comprehensive SR` for the Comprehensive "
        "SR IOD (D-010).",
        "",
        "An instance outside the supported scope whose IOD the pinned tables "
        "define, such as a nuclear medicine image or a spatial registration, "
        "is planned and edited, where its source can be read, only so that its "
        "values are collected for its subject's search; it is never written. "
        "An instance that the first pass read but whose values were not "
        "collected at all, since its source file was refused on its second "
        "read, its SOP Class names no IOD of the pinned tables, its transform "
        "raised an error, or its source file changed during the run, makes "
        "the release gate withhold every other file of its subject, by "
        "`not-reported`, since its values were not searched for in them "
        "(D-027). An input that the first pass sequesters for a sequence it "
        "cannot read has no known subject and withholds no other file.",
        "",
        "The report counts the instances held for review, by the stage that "
        "held each and its reason code, an instance once for each stage and "
        "code however many of its names or attributes have it (D-009):",
        "",
        *holding,
        "",
        "Where descriptor cleaning cleans ROI Names, the report counts the "
        "ROI Names of the structure sets it cleaned, each name by its "
        "outcome, as "
        + join((code(o.value) for o in RoiNameOutcome), "or")
        + ", and the distinct names it sent for review, whether then held "
        "or emptied unreviewed, each once for each of its reasons, by the "
        f"reason codes of {code('roi-names')} above, naming "
        "none of them (D-009).",
        "",
        "The report counts the instances that have each kind of first-pass "
        "reference finding that the run reports without acting on it, as "
        + join(sorted(code(kind.value) for kind in report.REPORTED_FINDINGS), "or")
        + ", each instance once for each kind, naming none of them (D-026).",
        "",
        "The report counts the released instances, and those held for "
        "review, that show each risk in their pixel data, as "
        + join((code(risk.value) for risk in pixel_risk.Risk), "or")
        + ", and each indicator of it, as "
        + join((code(indicator.value) for indicator in pixel_risk.Indicator), "or")
        + ", each instance once for each, an identical copy counting as the "
        "instance it copies, and names none of them (D-015). The indicators "
        "are read from the instances' attributes, and a volume's from its "
        "series; the pixel data are not inspected, so an instance without an "
        "indicator may still show the risk.",
        "",
        "The report summarises the engine's structural checks of the "
        "release, as "
        + join((code(check) for check in report.STRUCTURAL_CHECKS), "and")
        + ": how the inputs refer to each other, whether each written "
        "instance keeps the attributes that its IOD requires where its source "
        "had them, and whether what was written refers to itself as the "
        "inputs did. For each, it counts the instances that the check "
        "sequestered and those it reported without acting on them, each "
        "instance once, an identical copy counting as the instance it "
        "copies, naming none of them. The checks show that the release is consistent "
        "and well formed, not that it suits a particular use, which the "
        "person releasing the data confirms (D-016).",
        "",
        "The report counts the source values that the residual search did "
        "not search, in full or in part, by attribute, as tags from the "
        "outermost sequence without items, and by reason, each value once for "
        "each reason however many of its forms that reason left out (D-027). "
        f"A reason is one of those listed under Residual search, as {omissions}, "
        "or one by which the value is not given to the search at all:",
        "",
        *(
            f"- {code(reason.value)}: {UNSEARCHED_REASONS[reason]}."
            for reason in residuals.UnsearchedReason
        ),
        "",
        "The report lists each released instance by its output name alone, "
        "which is built from the replacement Patient ID and UIDs, and gives "
        "the run's QC pack by its opaque reference, with the outcome of its "
        "attestation (`attested`, `rejected`, or `not-attested`). With an "
        "attestation, it also records whether the person releasing the data "
        "confirmed in it that the output was checked for its intended use and "
        "that its residual risk was accepted, each true, false, or not stated, "
        "and nothing else of them. Every run writes a QC pack, so a report "
        "that a run writes always gives one. A report written before the pack "
        "is reviewed gives the outcome `not-attested`, with neither "
        "confirmation stated (D-016, D-026). An input that the run refuses, as "
        "not an instance that it can read, such as a symbolic link, a "
        "DICOMDIR, or a file not readable as DICOM, is neither labelled nor "
        "counted in the report; only the QC pack lists it. A run writes the "
        f"report at the root of the release as `{_RELEASE_REPORT}` and, beside "
        "it, its human-readable form as "
        f"`{_RELEASE_REPORT_MARKDOWN}`, generated from the report's text "
        "alone, which shows every value of the report and draws nothing else "
        "from it. Beside them, it writes this statement of its policy, which "
        f"holds no instance value, as `{_CONFORMANCE_STATEMENT}`.",
        "",
        "The report holds no source value or original path: each field is a "
        "digest, a version, a known edition, preset, or option, a file name "
        "or path within the engine's package, a QC pack's reference or an "
        "attestation outcome, an output name listed once, one of the run's "
        "labels, a path of tags, a code that the engine defines, a positive "
        "count, a structural check's count from 0, true or "
        "false, the report's or the method digest's format label, or none, and "
        "the report refuses any other. Only the confidential QC pack maps "
        "labels to source instances and lists each value not searched by "
        "instance and place (D-016).",
    ]
