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

from . import dummy_values, pseudonyms, residuals, uids
from . import release_report as report
from .conformance import ConformanceStatement
from .edits import PSEUDONYM_TAGS
from .release_report import _SEQUESTERING
from .residuals import _BINARY as _BINARY_VRS
from .residuals import _KINDS
from .residuals import _NUMBERS as _NUMBER_VRS
from .residuals import _PIXEL_DATA
from .values import CHECKED_VRS
from .walker import REVIEWED_DUMMY_SEQUENCES

TEMPORAL_MODIFIED = "(0028,0303)"  # Longitudinal Temporal Information Modified

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
    }
)


def _reviewed_items(named: Callable[[str], str]) -> list[str]:
    """Describe the item that D writes in each sequence with a reviewed rule."""
    lines = []
    for tag, compared in REVIEWED_DUMMY_SEQUENCES.items():
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
    return lines


def _naming_pymedphys(named: Callable[[str], str]) -> list[str]:
    """Name each value that a reviewed rule writes and that names PyMedPhys."""
    return [
        f"{named(element.tag)} `{element.value}`"
        for tag in REVIEWED_DUMMY_SEQUENCES
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
            f", except the {join(exceptions)} of the item above, which names "
            "who defines its code (D-021)."
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
        "written file for them, once the engine applies it to each run: the "
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
        "values by chance.",
        "",
        "These are not searched, and the search lists each by its source "
        "attribute and reason, never by its value:",
        "",
        *(f"- {OMISSIONS[reason]}." for reason in residuals.Omission),
        "",
        "Each finding names the value's kind, its source attribute, the form "
        "and encoding found, and its place in the file, never the value.",
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
        "is known.",
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
        "The report holds no source value or original path: each field is a "
        "digest, a version, a known edition, preset, or option, a file name "
        "or path within the engine's package, one of the run's labels, a path "
        "of tags, a code that the engine defines, a positive count, true or "
        "false, the report's or the method digest's format label, or none, and "
        "the report refuses any other. Only the confidential QC pack maps "
        "labels to source instances and lists each value not searched by "
        "instance and place (D-016).",
    ]
