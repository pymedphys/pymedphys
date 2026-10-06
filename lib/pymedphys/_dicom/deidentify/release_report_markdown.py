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

"""The release report's human-readable form.

:func:`to_markdown` gives the text of a release report as CommonMark with
GitHub Flavored Markdown tables, from
the JSON text that
:func:`~pymedphys._dicom.deidentify.release_report.to_json` writes and
nothing else, so that it can hold no value or path that the JSON lacks.
Every value of the document, and each file name that keys a digest, is shown
once for each time the document holds it, as a code span; everything outside
the code spans is fixed text that depends only on the document's shape. The
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
from collections.abc import Mapping, Sequence

from .release_report import FORMAT

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
    "generated_values_digest": "Generated values digest",
    "engine_files": None,
}
# The method's fields that are null where the run has none.
_OPTIONAL_METHOD = frozenset({"l3_rules", "vocabulary_digest", "reviewed_roi_names"})
_RUNTIME = {
    "pymedphys_version": "PyMedPhys",
    "python_implementation": "Python implementation",
    "python_version": "Python",
    "pydicom_version": "pydicom",
    "tomlkit_version": "tomlkit",
}
_SECTIONS = (
    "format",
    "policy",
    "method",
    "runtime",
    "qc_review",
    "released",
    "sequestered",
    "held_for_review",
    "roi_names",
    "reference_findings",
    "search_coverage",
    "source_gaps",
)
_NONE = "None."


class ReleaseReportMarkdownError(ValueError):
    """The text is not a release report of this module's format.

    The message names the field, never its value.
    """


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
        *_qc_review(document["qc_review"]),
        *_released(document["released"]),
        *_sequestered(document["sequestered"]),
        *_held(document["held_for_review"]),
        *_roi_names(document["roi_names"]),
        *_reference_findings(document["reference_findings"]),
        *_coverage(document["search_coverage"]),
        *_gaps(document["source_gaps"]),
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


def _qc_review(section: object) -> list[Block]:
    heading = ["## QC review"]
    if section is None:
        return [heading, ["No QC pack was written for this run."]]
    section = _fields("qc_review", section, ("reference", "outcome"))
    return [
        heading,
        [
            "The run's confidential QC pack, by its opaque reference, and the "
            "outcome of a reviewer's attestation of it."
        ],
        _table(
            ("Field", "Value"),
            [
                ("Reference", _code("qc_review reference", section["reference"])),
                ("Attestation", _code("qc_review outcome", section["outcome"])),
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


def _roi_names(section: object) -> list[Block]:
    section = _fields("roi_names", section, ("outcomes", "held"))
    tables = []
    for field, key, header in (
        ("outcomes", "outcome", ("Outcome", "Names")),
        ("held", "reason", ("Reason", "Distinct names")),
    ):
        rows = []
        for entry in _list(f"roi_names {field}", section[field]):
            entry = _fields(f"roi_names {field}", entry, (key, "count"))
            rows.append(
                (
                    _code(f"roi_names {key}", entry[key]),
                    _count(f"roi_names {field} count", entry["count"]),
                )
            )
        tables.append(_table(header, rows) if rows else [_NONE])
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


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> Block:
    def line(cells: Sequence[str]) -> str:
        return "|" + "".join(f" {cell} |" if cell else " |" for cell in cells)

    return [line(header), "|" + " --- |" * len(header), *(line(row) for row in rows)]


def _digest_table(field: str, digests: object) -> Block:
    if not isinstance(digests, dict):
        raise _refuse(field)
    return _table(
        ("File", "SHA-256"),
        [
            (_code(field, name), _code(field, digest))
            for name, digest in digests.items()
        ],
    )


def _fields(
    field: str, section: object, names: Mapping[str, object] | Sequence[str]
) -> dict:
    """Return the section, if it has exactly these fields, in this order."""
    if not isinstance(section, dict) or list(section) != list(names):
        raise ReleaseReportMarkdownError(
            f"The fields of the release report's {field} are not those of {FORMAT}."
        )
    return section


def _list(field: str, value: object) -> list:
    if not isinstance(value, list):
        raise _refuse(field)
    return value


def _code(field: str, value: object) -> str:
    # An empty code span, or one with space at an end, would not show the
    # value as it is.
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(c in value for c in "`|\n\r")
    ):
        raise _refuse(field)
    return f"`{value}`"


def _count(field: str, value: object) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _refuse(field)
    return f"`{value}`"


def _boolean(field: str, value: object) -> str:
    if not isinstance(value, bool):
        raise _refuse(field)
    return f"`{json.dumps(value)}`"


def _optional(field: str, value: object, absent: str = "none") -> str:
    return absent if value is None else _code(field, value)


def _members(pairs: list[tuple[str, object]]) -> dict:
    """Return a JSON object's members, refusing a member named twice."""
    members = dict(pairs)
    if len(members) != len(pairs):
        raise ReleaseReportMarkdownError(
            "The release report names a member twice in one object."
        )
    return members


def _refuse(field: str) -> ReleaseReportMarkdownError:
    return ReleaseReportMarkdownError(
        f"The release report's {field} is not in the form of {FORMAT}."
    )
