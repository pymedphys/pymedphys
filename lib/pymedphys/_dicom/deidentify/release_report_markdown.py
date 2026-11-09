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

# pylint: disable = too-many-lines
# One module renders every section of the report, each checked as it is
# read, so it is long.

"""The release report's human-readable form.

:func:`to_markdown` gives the text of a release report as CommonMark with
GitHub Flavored Markdown tables, from
the JSON text that
:func:`~pymedphys._dicom.deidentify.release_report.to_json` writes and
nothing else, so that it can hold no value or path that the JSON lacks.
Every value of the document, and each file name that keys a digest, is shown
once for each time the document holds it, as a code span; everything outside
the code spans is fixed text that depends only on the document's shape, but
for the caution that follows the policy where it selects the Retain UIDs
Option, since kept UIDs link the release to its source (PS3.15 E.3.9). The
sections follow the document's order, with a table for each, and the same
text always gives the same form. The JSON remains the record.

The document must have exactly the sections and fields of
:data:`~pymedphys._dicom.deidentify.release_report.FORMAT`, in order, each
reason with the fields that its stage gives, and values of their JSON types,
each text non-empty, without a backtick, a vertical bar, a line break, or
space at either end, and no member named twice; any other text is refused
with a message that names the field, never its value. The forms of the
values themselves, such as digests and codes, are those that
:func:`~pymedphys._dicom.deidentify.release_report.to_json` checks.
"""

from __future__ import annotations

import json

from .policy import UIDS
from .release_report import FORMAT, STRUCTURAL_CHECKS
from .release_report_markdown_values import (
    ReleaseReportMarkdownError,
    _boolean,
    _code,
    _count,
    _digest_table,
    _fields,
    _list,
    _members,
    _optional,
    _refuse,
    _table,
    _tally,
)

# The name of each field of a section, as a reader sees it, in the order of
# the document.
_POLICY = {
    "preset": "Preset",
    "edition": "PS3.15 edition",
    "options": "Options",
    "claims_conformance": "Can claim conformance",
}
_METHOD = {
    "method_digest": "Method digest",
    "method_digest_format": "Method digest format",
    "engine_version": "Engine version",
    "table_digests": None,
    "l2_rules_digest": "L2 rules digest",
    "l3_rules": "L3 rules",
    "vocabulary_digest": "Vocabulary digest",
    "reviewed_roi_names": "Reviewed ROI names digest",
    "reviewed_descriptors": "Reviewed descriptors digest",
    "technique_vocabulary_digest": "Technique vocabulary digest",
    "text_finder_digest": "Text finder digest",
    "pixel_region_rules": "Pixel region rules digest",
    "safe_private_list": "Safe private list",
    "generated_values_digest": "Generated values digest",
    "engine_files": None,
}
# The method's fields that are null where the run has none.
_OPTIONAL_METHOD = frozenset(
    {
        "l3_rules",
        "vocabulary_digest",
        "reviewed_roi_names",
        "reviewed_descriptors",
        "technique_vocabulary_digest",
        "text_finder_digest",
        "pixel_region_rules",
        "safe_private_list",
    }
)
_RUNTIME = {
    "pymedphys_version": "PyMedPhys",
    "python_implementation": "Python implementation",
    "python_version": "Python",
    "pydicom_version": "pydicom",
    "tomlkit_version": "tomlkit",
}
_CONFIRMATIONS = {
    "intended_use_checked": "Intended use checked",
    "residual_risk_accepted": "Residual risk accepted",
}
_SECTIONS = (
    "format",
    "policy",
    "method",
    "runtime",
    "key",
    "qc_review",
    "face_review",
    "redaction_review",
    "pixel_regions",
    "readiness",
    "released",
    "sequestered",
    "held_for_review",
    "roi_names",
    "descriptors",
    "icc_profiles",
    "reference_findings",
    "pixel_risks",
    "search_coverage",
    "exempted_findings",
    "source_gaps",
    "structural_checks",
    "studies_with_several_patients",
)
_NONE = "None."
# The readiness section's gates, as a reader sees them, in the order of the
# document.
_GATES = {
    "statistical": "Statistical gate",
    "pixel_and_face": "Pixel and face review gate",
    "attestation": "Attestation gate",
}


def to_markdown(report: str) -> str:
    """Return a release report's JSON text as CommonMark.

    Parameters
    ----------
    report : str
        The text that
        :func:`~pymedphys._dicom.deidentify.release_report.to_json` gives.

    Returns
    -------
    str
        The report as CommonMark, ending with one line break.

    Raises
    ------
    ReleaseReportMarkdownError
        If the text is not JSON, or not a document of
        :data:`~pymedphys._dicom.deidentify.release_report.FORMAT`.
    """
    try:
        document = json.loads(report, object_pairs_hook=_members)
    except ReleaseReportMarkdownError:
        raise
    except (TypeError, ValueError):
        raise ReleaseReportMarkdownError("The release report is not JSON.") from None
    document = _fields("top level", document, _SECTIONS)
    if document["format"] != FORMAT:
        raise ReleaseReportMarkdownError(
            "The release report's format is not " + FORMAT + "."
        )
    blocks = [
        ["# De-identification release report"],
        [
            f"Format {_code('format', document['format'])}. This is the "
            "human-readable form of release-report.json, generated from it "
            "alone; that file is the record. Neither holds a value from the "
            "source files or an original path."
        ],
        *_policy(document["policy"]),
        *_method(document["method"]),
        *_runtime(document["runtime"]),
        *_key(document["key"]),
        *_qc_review(document["qc_review"]),
        *_face_review(document["face_review"]),
        *_redaction_review(document["redaction_review"]),
        *_pixel_regions(document["pixel_regions"]),
        *_readiness(document["readiness"]),
        *_released(document["released"]),
        *_sequestered(document["sequestered"]),
        *_held(document["held_for_review"]),
        *_roi_names(document["roi_names"]),
        *_descriptors(document["descriptors"]),
        *_icc_profiles(document["icc_profiles"]),
        *_reference_findings(document["reference_findings"]),
        *_pixel_risks(document["pixel_risks"]),
        *_coverage(document["search_coverage"]),
        *_exempted(document["exempted_findings"]),
        *_gaps(document["source_gaps"]),
        *_structural_checks(document["structural_checks"]),
        *_several_patients(document["studies_with_several_patients"]),
    ]
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


Block = list[str]


def _policy(section: object) -> list[Block]:
    section = _fields("policy", section, _POLICY)
    preset = section["preset"]
    options = _list("policy options", section["options"])
    return [
        ["## Policy"],
        [
            "The PS3.15 edition, preset, and Options that the run applied, and "
            "whether the policy can claim conformance to PS3.15."
        ],
        _table(
            ("Field", "Value"),
            [
                (
                    _POLICY["preset"],
                    "none (a custom option set)"
                    if preset is None
                    else _code("policy preset", preset),
                ),
                (_POLICY["edition"], _code("policy edition", section["edition"])),
                (
                    _POLICY["options"],
                    ", ".join(_code("policy options", each) for each in options)
                    or "none",
                ),
                (
                    _POLICY["claims_conformance"],
                    _boolean(
                        "policy claims_conformance", section["claims_conformance"]
                    ),
                ),
            ],
        ),
        *_kept_uids(options),
    ]


def _kept_uids(options: list[object]) -> list[Block]:
    """Warn that kept UIDs link the release to its source (PS3.15 E.3.9)."""
    if UIDS not in options:
        return []
    return [
        [
            "Under the Retain UIDs Option, the released instances keep their "
            "source UIDs, such as their SOP Instance, Series Instance, and "
            "Study Instance UIDs, as Table E.1-1 lists them. Anyone with access "
            "to the source images, or to a database of them, can link each "
            "released instance to its source by them, and so recover the "
            "patient's identity (PS3.15 E.3.9)."
        ]
    ]


def _method(section: object) -> list[Block]:
    section = _fields("method", section, _METHOD)
    rows = [
        (
            label,
            _optional(f"method {name}", section[name])
            if name in _OPTIONAL_METHOD
            else _code(f"method {name}", section[name]),
        )
        for name, label in _METHOD.items()
        if label is not None
    ]
    return [
        ["## Method"],
        [
            "The method digest, which De-identification Method (0012,0063) of "
            "each released instance records, with the components it is "
            "computed from."
        ],
        _table(("Field", "Value"), rows),
        ["### Standard tables"],
        _digest_table("method table_digests", section["table_digests"]),
        ["### Engine files"],
        _digest_table("method engine_files", section["engine_files"]),
    ]


def _runtime(section: object) -> list[Block]:
    section = _fields("runtime", section, _RUNTIME)
    return [
        ["## Runtime environment"],
        [
            "The versions that ran, which Software Versions (0018,1020) of the "
            "de-identifying equipment records."
        ],
        _table(
            ("Software", "Version"),
            [
                (label, _code(f"runtime {name}", section[name]))
                for name, label in _RUNTIME.items()
            ],
        ),
    ]


def _key(section: object) -> list[Block]:
    section = _fields("key", section, ("scope", "key_id"))
    scope, key_id = section["scope"], section["key_id"]
    if (scope, key_id is None) not in (("run", True), ("project", False)):
        raise _refuse("key")
    return [
        ["## Key"],
        [
            "The scope of the key that the run's replacement UIDs, "
            "pseudonyms, and date offsets were derived under: run, for a key "
            "of this run alone, whose values agree with no other run's, or "
            "project, for a project key, named by its non-secret identifier, "
            "whose values agree with every other release under that key, so "
            "that those releases can be linked to each other."
        ],
        _table(
            ("Field", "Value"),
            [
                ("Scope", _code("key scope", scope)),
                ("Key identifier", _optional("key key_id", key_id)),
            ],
        ),
    ]


def _qc_review(section: object) -> list[Block]:
    heading = ["## QC review"]
    if section is None:
        return [heading, ["No QC pack was written for this run."]]
    section = _fields("qc_review", section, ("reference", "outcome", *_CONFIRMATIONS))
    return [
        heading,
        [
            "The run's confidential QC pack, by its opaque reference, the "
            "outcome of a reviewer's attestation of it, and whether the person "
            "releasing the data confirmed in it that the output was checked "
            "for its intended use and that its residual risk was accepted."
        ],
        _table(
            ("Field", "Value"),
            [
                ("Reference", _code("qc_review reference", section["reference"])),
                ("Attestation", _code("qc_review outcome", section["outcome"])),
                *(
                    (
                        label,
                        "not stated"
                        if section[name] is None
                        else _boolean(f"qc_review {name}", section[name]),
                    )
                    for name, label in _CONFIRMATIONS.items()
                ),
            ],
        ),
    ]


def _face_review(section: object) -> list[Block]:
    if section is None:
        return []
    section = _fields(
        "face_review",
        section,
        (
            "reference",
            "ct_series",
            "rt_doses_in_face_block",
            "undefaced_in_defaced_frame",
        ),
    )
    series = _fields(
        "face_review ct_series",
        section["ct_series"],
        (
            "defaced",
            "defaced_around_targets",
            "defaced_eyes_unconfirmed",
            "defaced_eyes_confirmed",
            "not_defaced",
        ),
    )
    rows = []
    for entry in _list("face_review ct_series not_defaced", series["not_defaced"]):
        entry = _fields("face_review ct_series not_defaced", entry, ("reason", "count"))
        rows.append(
            (
                _code("face_review ct_series reason", entry["reason"]),
                _count("face_review ct_series count", entry["count"]),
            )
        )
    return [
        ["## Face review"],
        [
            "Under the Clean Recognizable Visual Features Option, an instance "
            "that can show a face is released only where a reviewer saw no "
            "recognisable face in its series, in the earlier run's confidential "
            "QC pack with this opaque reference: "
            + _code("face_review reference", section["reference"])
            + "."
        ],
        [
            "Series of CT instances whose face block the run wrote as air: "
            + _tally("face_review ct_series defaced", series["defaced"])
            + ". Of those, the series in whose block the run kept a "
            "target's region, a PTV, CTV, or GTV with whatever lies between "
            "its contours, which the reviewer's verdict on the written "
            "images decides: "
            + _tally(
                "face_review ct_series defaced_around_targets",
                series["defaced_around_targets"],
            )
            + ". Of the series defaced, those whose eye ROIs lie away from "
            "the eyes that the run found, which it holds for review, with each "
            "instance cleaned by their block, until a reviewer confirms the "
            "block from the QC pack's sheet of the eyes: "
            + _tally(
                "face_review ct_series defaced_eyes_unconfirmed",
                series["defaced_eyes_unconfirmed"],
            )
            + "; and those whose block a reviewer confirmed, which the "
            "reviewer's verdict on the written images decides: "
            + _tally(
                "face_review ct_series defaced_eyes_confirmed",
                series["defaced_eyes_confirmed"],
            )
            + ". Those it did not deface, by reason, which the reviewer's "
            "verdict decides, or, for a target that the run cannot keep "
            "within the images, holds for review:"
        ],
        _table(("Reason", "Series"), rows) if rows else [_NONE],
        *_doses_in_face_block(section["rt_doses_in_face_block"]),
        *_undefaced_in_defaced_frame(section["undefaced_in_defaced_frame"]),
    ]


def _undefaced_in_defaced_frame(section: object) -> list[Block]:
    field = "face_review undefaced_in_defaced_frame"
    undefaced = _fields(field, section, ("held", "released", "held_with_own_verdict"))
    rows = [
        (_code(f"{field} released", output),)
        for output in _list(f"{field} released", undefaced["released"])
    ]
    return [
        [
            "RT Structure Sets, RT Doses, PET images, Segmentations, and "
            "deformable registrations in the Frame of Reference of a defaced "
            "CT series, naming none, or referring to a defaced slice, that the "
            "run does not clean of the face, wholly, or of a defaced slice "
            "that they refer to in another frame, which a verdict on their "
            "series does not release, since it may have been given beside the "
            "defaced CT, and which are released only where a reviewer saw no "
            "recognisable face in each one's own previews: held without such "
            "a verdict: "
            + _tally(f"{field} held", undefaced["held"])
            + "; held with one, since it or its series showed a face, the run "
            "writes other pixel data, contours, or deformation grids of it "
            "than the QC pack showed, a block of its own frame that cleaned "
            "it awaits confirmation, or another hold applies: "
            + _tally(
                f"{field} held_with_own_verdict", undefaced["held_with_own_verdict"]
            )
            + ". Each released on its own verdict, by its output name, is "
            "written as the QC pack showed it: not cleaned of the face, or "
            "cleaned only by the blocks of its own frame:"
        ],
        _table(("Output name",), rows) if rows else [_NONE],
    ]


def _doses_in_face_block(section: object) -> list[Block]:
    field = "face_review rt_doses_in_face_block"
    doses = _fields(
        field,
        section,
        (
            "held",
            "released_as_written",
            "held_as_written",
            "released_set_to_zero",
            "held_set_to_zero",
        ),
    )
    rows = [
        (_code(f"{field} {name}", output), what)
        for name, what in (
            ("released_as_written", "written as received"),
            ("released_set_to_zero", "set to zero in the face block"),
        )
        for output in _list(f"{field} {name}", doses[name])
    ]
    return [
        [
            "RT Doses with more dose in a face block than the run sets to zero "
            "there, which it writes as received and holds for review until a "
            "reviewer chooses, for a later run, to have each written as "
            "received, released only where the reviewer saw no recognisable "
            "face in its own dose levels, or set to zero there anyway, "
            "released only where a reviewer saw no recognisable face in a "
            "later QC pack's dose levels of it so: held without a choice: "
            + _tally(f"{field} held", doses["held"])
            + "; held, written as received on a reviewer's choice: "
            + _tally(f"{field} held_as_written", doses["held_as_written"])
            + "; held, set to zero on a reviewer's choice: "
            + _tally(f"{field} held_set_to_zero", doses["held_set_to_zero"])
            + ". Each released on a reviewer's choice, by its output name; one "
            "set to zero may have lost dose that matters for planning, such as "
            "a target's that the structure set does not mark, and its "
            "dose-volume histograms are those of the grid as received:"
        ],
        _table(("Output name", "Dose in the face block"), rows) if rows else [_NONE],
    ]


def _redaction_review(section: object) -> list[Block]:
    if section is None:
        return []
    section = _fields(
        "redaction_review", section, ("reference", "review_modes", "frames_not_shown")
    )
    modes = _fields(
        "redaction_review review_modes",
        section["review_modes"],
        ("every-frame", "flagged-frames"),
    )
    every = _tally("redaction_review review_modes", modes["every-frame"])
    flagged = _tally("redaction_review review_modes", modes["flagged-frames"])
    not_shown = _tally("redaction_review frames_not_shown", section["frames_not_shown"])
    return [
        ["## Redaction review"],
        [
            "Under the Clean Pixel Data Option, an instance with Pixel Data is "
            "released only where a reviewer confirmed the regions to black "
            "out, keeping or dropping those that the text finder proposed and "
            "adding their own, in the earlier run's confidential QC pack with "
            "this opaque reference: "
            + _code("redaction_review reference", section["reference"])
            + ". Source files so approved whose review required every frame: "
            f"{every}; whose review required only the frames with a "
            "proposed region, which only an IOD whose text finder met the "
            f"acceptance criteria allows: {flagged}. Frames of those files "
            f"that the reviewer was not shown: {not_shown}."
        ],
    ]


def _pixel_regions(section: object) -> list[Block]:
    if section is None:
        return []
    section = _fields("pixel_regions", section, ("detected", "rule"))
    return [
        ["## Pixel regions"],
        [
            "Under the Clean Pixel Data Option, the regions blacked out in the "
            "instances released or held without a reviewer's verdict, each "
            "region once in each frame that has it, by what gave them. A "
            "reviewed region rule gives regions to every frame of an instance "
            "of one kind, beside those that the text finder finds."
        ],
        _table(
            ("Source", "Regions"),
            [
                ("Text finder", _tally("pixel_regions detected", section["detected"])),
                ("Region rules", _tally("pixel_regions rule", section["rule"])),
            ],
        ),
    ]


def _readiness(section: object) -> list[Block]:
    if section is None:
        return []
    section = _fields("readiness", section, ("ready", "review", "assessment", *_GATES))
    return [
        ["## Readiness for public release"],
        [
            "Under the `public-release` preset, the run is ready for release "
            "only where three gates pass: the statistical gate, from the risk "
            "assessment recorded beside the earlier run's confidential QC pack "
            "that the run was given, and the pixel and face review and human "
            "QC attestation gates, from that pack's attestation. Passing one "
            "passes no other, and a gate that failed gives the first reason "
            "that held."
        ],
        _table(
            ("Field", "Value"),
            [
                ("Ready", _boolean("readiness ready", section["ready"])),
                (
                    "Reviewed QC pack",
                    _optional("readiness review", section["review"]),
                ),
                (
                    "Risk assessment",
                    _optional("readiness assessment", section["assessment"]),
                ),
                *(
                    (
                        label,
                        _optional(f"readiness {name}", section[name], "passed"),
                    )
                    for name, label in _GATES.items()
                ),
            ],
        ),
    ]


def _released(section: object) -> list[Block]:
    names = _list("released", section)
    return [
        ["## Released instances"],
        [
            "Each released instance by its output name, the path of its file "
            "below the release."
        ],
        _table(("Output name",), [(_code("released", name),) for name in names])
        if names
        else [_NONE],
    ]


_REASON = ("stage", "code", "attribute", "action", "vr", "iod")
# The fields of a reason from each stage, as the report gives them: the
# walker's VR may be null, the release gate names an attribute at most, and
# scope names the IOD of an unsupported IOD.
_WALKER = ("stage", "code", "attribute", "action", "vr")
_RELEASE = (("stage", "code"), ("stage", "code", "attribute"))
_UNSUPPORTED_IOD = ("stage", "code", "iod")


def _sequestered(section: object) -> list[Block]:
    rows = []
    for instance in _list("sequestered", section):
        instance = _fields("sequestered", instance, ("label", "reasons"))
        label = _code("sequestered label", instance["label"])
        reasons = _list("sequestered reasons", instance["reasons"])
        if not reasons:
            raise _refuse("sequestered reasons")
        for position, reason in enumerate(reasons):
            reason = _reason(reason)
            rows.append(
                (
                    # The label heads its instance's first reason only.
                    "" if position else label,
                    *(
                        _optional(f"sequestered {name}", reason.get(name), "")
                        if name == "vr"
                        else _code(f"sequestered {name}", reason[name])
                        if name in reason
                        else ""
                        for name in _REASON
                    ),
                )
            )
    return [
        ["## Sequestered instances"],
        [
            "Each sequestered instance by a label drawn at random for the run, "
            "on the first of its rows, with each reason's stage and code, and, where the reason names "
            "them, the attribute's tags, the action, the VR, and the IOD. Only "
            "the confidential QC pack maps labels to source files."
        ],
        _table(("Label", "Stage", "Code", "Attribute", "Action", "VR", "IOD"), rows)
        if rows
        else [_NONE],
    ]


def _reason(reason: object) -> dict:
    """Return a reason, if it has the fields that its stage gives, in order."""
    stage, code = (
        (reason.get("stage"), reason.get("code"))
        if isinstance(reason, dict)
        else (None, None)
    )
    if stage == "walker":
        return _fields("sequestered reasons", reason, _WALKER)
    if (stage, code) == ("scope", "unsupported-iod"):
        return _fields("sequestered reasons", reason, _UNSUPPORTED_IOD)
    shapes = _RELEASE if stage == "release" else _RELEASE[:1]
    if not isinstance(reason, dict) or tuple(reason) not in shapes:
        raise _refuse("sequestered reasons")
    return reason


def _held(section: object) -> list[Block]:
    rows = []
    for entry in _list("held_for_review", section):
        entry = _fields("held_for_review", entry, ("stage", "code", "count"))
        rows.append(
            (
                _code("held_for_review stage", entry["stage"]),
                _code("held_for_review code", entry["code"]),
                _count("held_for_review count", entry["count"]),
            )
        )
    return [
        ["## Instances held for review"],
        [
            "How many instances were held for review for each stage and reason, "
            "each instance once for each of its reasons. Held instances are "
            "neither released nor named."
        ],
        _table(("Stage", "Code", "Instances"), rows) if rows else [_NONE],
    ]


def _code_tables(name: str, section: dict, counted: str) -> list[Block]:
    """Return the tables of a section's ``outcomes`` and ``held`` counts."""
    tables = []
    for field, key, header in (
        ("outcomes", "outcome", ("Outcome", counted.capitalize())),
        ("held", "reason", ("Reason", f"Distinct {counted}")),
    ):
        rows = []
        for entry in _list(f"{name} {field}", section[field]):
            entry = _fields(f"{name} {field}", entry, (key, "count"))
            rows.append(
                (
                    _code(f"{name} {key}", entry[key]),
                    _count(f"{name} {field} count", entry["count"]),
                )
            )
        tables.append(_table(header, rows) if rows else [_NONE])
    return tables


def _roi_names(section: object) -> list[Block]:
    section = _fields("roi_names", section, ("outcomes", "held"))
    tables = _code_tables("roi_names", section, "names")
    return [
        ["## ROI names"],
        [
            "The outcome of each ROI Name of the structure sets that descriptor "
            "cleaning cleaned, every name counted, and how many distinct names "
            "it sent for review for each reason, whether they were then held "
            "or emptied unreviewed. Only the confidential QC pack lists the "
            "names."
        ],
        ["### Outcome of each name"],
        tables[0],
        ["### Distinct names sent for review"],
        tables[1],
    ]


def _descriptors(section: object) -> list[Block]:
    section = _fields("descriptors", section, ("outcomes", "held", "fell_back"))
    tables = _code_tables("descriptors", section, "values")
    return [
        ["## Descriptors"],
        [
            "The outcome of each value of the free-text descriptors that "
            "descriptor cleaning read, every value counted, how many distinct "
            "values, each of one attribute, it sent for review for each "
            "reason, and how many elements were not written with what "
            "cleaning gave their values and took their action without Clean "
            "Descriptors instead. Only the confidential QC pack lists the "
            "values."
        ],
        ["### Outcome of each value"],
        tables[0],
        ["### Distinct values sent for review"],
        tables[1],
        [
            "Elements that took their action without Clean Descriptors: "
            f"{_tally('descriptors fell_back', section['fell_back'])}."
        ],
    ]


def _icc_profiles(section: object) -> list[Block]:
    section = _fields("icc_profiles", section, ("cleaned", "replaced"))
    rows = []
    for entry in _list("icc_profiles replaced", section["replaced"]):
        entry = _fields("icc_profiles replaced", entry, ("reason", "count"))
        rows.append(
            (
                _code("icc_profiles reason", entry["reason"]),
                _count("icc_profiles replaced count", entry["count"]),
            )
        )
    return [
        ["## ICC profiles"],
        [
            "What replaced the ICC Profile of each released and held instance "
            "that had one: the source profile cleaned of everything but its "
            "colorimetry, so that colours show as they did in the source, or, "
            "where the source could not be cleaned, a fixed sRGB profile, "
            "with which colours can show differently."
        ],
        [
            "Cleaned source profiles: "
            f"{_tally('icc_profiles cleaned', section['cleaned'])}."
        ],
        ["### Fixed sRGB profiles, by why the source could not be cleaned"],
        _table(("Reason", "Profiles"), rows) if rows else [_NONE],
    ]


def _reference_findings(section: object) -> list[Block]:
    rows = []
    for entry in _list("reference_findings", section):
        entry = _fields("reference_findings", entry, ("kind", "count"))
        rows.append(
            (
                _code("reference_findings kind", entry["kind"]),
                _count("reference_findings count", entry["count"]),
            )
        )
    return [
        ["## Reference findings"],
        [
            "How many instances have each kind of reference finding that the "
            "run reported without acting on it, such as a reference that names "
            "no instance of the run, each instance once for each kind. Only "
            "the confidential QC pack lists them."
        ],
        _table(("Kind", "Instances"), rows) if rows else [_NONE],
    ]


def _pixel_risks(section: object) -> list[Block]:
    section = _fields("pixel_risks", section, ("instances", "indicators"))
    tables = []
    for field, keys, header in (
        ("instances", ("disposition", "risk"), ("Disposition", "Risk", "Instances")),
        (
            "indicators",
            ("disposition", "risk", "indicator"),
            ("Disposition", "Risk", "Indicator", "Instances"),
        ),
    ):
        rows = []
        for entry in _list(f"pixel_risks {field}", section[field]):
            entry = _fields(f"pixel_risks {field}", entry, (*keys, "count"))
            rows.append(
                (
                    *(_code(f"pixel_risks {key}", entry[key]) for key in keys),
                    _count(f"pixel_risks {field} count", entry["count"]),
                )
            )
        tables.append(_table(header, rows) if rows else [_NONE])
    return [
        ["## Pixel data risks"],
        [
            "How many released instances, and how many held for review, show "
            "each risk in their pixel data, and each indicator of it, each "
            "instance once for each. The indicators are read from the "
            "instances' attributes, and a volume's from its series; the "
            "pixel data are not inspected for them, so an instance without "
            "an indicator may still show the risk. Only the confidential QC "
            "pack lists the instances."
        ],
        ["### Instances with each risk"],
        tables[0],
        ["### Instances with each indicator"],
        tables[1],
    ]


def _coverage(section: object) -> list[Block]:
    rows = []
    for entry in _list("search_coverage", section):
        entry = _fields("search_coverage", entry, ("attribute", "reason", "count"))
        rows.append(
            (
                _code("search_coverage attribute", entry["attribute"]),
                _code("search_coverage reason", entry["reason"]),
                _count("search_coverage count", entry["count"]),
            )
        )
    return [
        ["## Values not searched"],
        [
            "How many source values of each attribute the residual search did "
            "not search, in full or in part, for each reason. The QC "
            "pack lists each by instance and place."
        ],
        _table(("Attribute", "Reason", "Values"), rows) if rows else [_NONE],
    ]


def _exempted(section: object) -> list[Block]:
    rows = []
    for entry in _list("exempted_findings", section):
        entry = _fields(
            "exempted_findings", entry, ("exemption", "attribute", "found_in", "count")
        )
        rows.append(
            (
                _code("exempted_findings exemption", entry["exemption"]),
                _code("exempted_findings attribute", entry["attribute"]),
                _code("exempted_findings found_in", entry["found_in"]),
                _count("exempted_findings count", entry["count"]),
            )
        )
    return [
        ["## Residual findings exempted from review"],
        [
            "How many released instances have a source value that the residual "
            "search found but that neither held nor withheld the instance, "
            "because what it is or where it was found explains it: a standard "
            "term or code, an equipment name, a vendor's private creator, a date "
            "that Modified Dates shifted, a value that a selected option keeps, "
            "text in a private creator that the run's safe private list keeps, "
            "or a standard code's meaning, or a UID that a selected option "
            "keeps, that only instances the run did not write held, or a "
            "kept code meaning made only of the reviewed technique vocabulary. "
            "Each is "
            "counted by why it was exempted, the attribute that "
            "held the source value, and the attribute it was found in, each "
            "instance once for each. The QC pack lists each finding by instance "
            "and place."
        ],
        _table(("Exemption", "Attribute", "Found in", "Instances"), rows)
        if rows
        else [_NONE],
    ]


def _gaps(section: object) -> list[Block]:
    rows = []
    for entry in _list("source_gaps", section):
        entry = _fields("source_gaps", entry, ("attribute", "type", "count"))
        rows.append(
            (
                _code("source_gaps attribute", entry["attribute"]),
                _code("source_gaps type", entry["type"]),
                _count("source_gaps count", entry["count"]),
            )
        )
    return [
        ["## Required attributes missing from the source"],
        [
            "How many instances' source files lack each attribute that their "
            "IOD unconditionally requires, by its Type. The run reports these "
            "and does not act on them: an instance is never withheld for what "
            "its source lacked. The QC pack lists each by instance and place."
        ],
        _table(("Attribute", "Type", "Instances"), rows) if rows else [_NONE],
    ]


def _structural_checks(section: object) -> list[Block]:
    entries = [
        _fields("structural_checks", entry, ("check", "sequestered", "reported"))
        for entry in _list("structural_checks", section)
    ]
    if [entry["check"] for entry in entries] != list(STRUCTURAL_CHECKS):
        raise _refuse("structural_checks")
    return [
        ["## Structural checks"],
        [
            "The engine's checks that the release is well formed and refers to "
            "itself as the source did: how the inputs refer to each other, "
            "whether each written instance keeps the attributes that its IOD "
            "requires, and whether what was written refers to itself as the "
            "inputs did. For each, how many instances it sequestered and how "
            "many it reported without acting on them, each instance once. The "
            "confidential QC pack names them. These checks show that the "
            "release is consistent, not that it suits a particular use."
        ],
        _table(
            ("Check", "Sequestered", "Reported"),
            [
                (
                    _code("structural_checks check", entry["check"]),
                    _tally("structural_checks sequestered", entry["sequestered"]),
                    _tally("structural_checks reported", entry["reported"]),
                )
                for entry in entries
            ],
        ),
    ]


# The run's choices for a study whose instances name several patients.
_SEVERAL_PATIENTS = ("stop", "sequester")


def _several_patients(section: object) -> list[Block]:
    section = _fields(
        "studies_with_several_patients", section, ("handling", "sequestered")
    )
    handling = section["handling"]
    if handling not in _SEVERAL_PATIENTS:
        raise _refuse("studies_with_several_patients handling")
    sequestered = _tally(
        "studies_with_several_patients sequestered", section["sequestered"]
    )
    if handling == "stop" and section["sequestered"]:
        raise _refuse("studies_with_several_patients sequestered")
    return [
        ["## Studies with several patients"],
        [
            "What the run did with a study whose instances name several "
            "patients, each a Patient ID with its issuer, which is a curation "
            "error that no change to its instances can repair: stop, the "
            "default, under which such a study stops the run before anything "
            "is written, or sequester, the opt-in under which each instance of "
            "such a study is sequestered for study-with-several-patients and "
            "the rest of the run goes ahead. A sequestered study's values were "
            "still searched for in the released files of every patient that it "
            "names. Where the run sequestered one, this release lacks every "
            "instance of it, so the record of each patient that it names is "
            "incomplete. The confidential QC pack lists the instances of each study by "
            "patient, for a curator to correct."
        ],
        _table(
            ("Field", "Value"),
            [
                ("Handling", _code("studies_with_several_patients", handling)),
                ("Studies sequestered", sequestered),
            ],
        ),
    ]
