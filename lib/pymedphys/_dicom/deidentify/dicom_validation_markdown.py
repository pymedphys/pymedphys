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

"""Render a DICOM validation comparison as CommonMark.

The comparison's JSON document
(:meth:`~pymedphys._dicom.deidentify.dicom_validation.Comparison.json`) holds
no value or path, and nor does what this renders from it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from pymedphys._imports import pydicom

_TAG = re.compile(r"^\(([0-9A-F]{4}),([0-9A-F]{4})\)$")
_OUTCOMES = (
    ("unexplained", "Unexplained"),
    ("explained", "Explained"),
    ("not comparable", "Not comparable"),
)


def render_markdown(document: Mapping[str, object]) -> str:
    """Render a comparison's JSON document as CommonMark."""
    versions = document["versions"]
    tallies = document["tallies"]
    introduced = document["introduced"]
    assert isinstance(versions, Mapping) and isinstance(tallies, Mapping)
    assert isinstance(introduced, list)
    verdict = (
        "**Passed**: the de-identification introduced no unexplained finding."
        if document["passed"]
        else "**Failed**: the de-identification introduced unexplained findings, "
        "listed below."
    )
    lines = [
        "# DICOM validation of a de-identified release",
        "",
        "Independent validators checked each released instance's input and "
        "output. A finding is **introduced** where the output gives it more "
        "often than its input; findings the input already had are not "
        "charged to the de-identification.",
        "",
        verdict,
        "",
        "## Versions",
        "",
        _table(
            ("Item", "Version"),
            [
                ("dicom3tools", versions["dicom3tools"]),
                ("dicom-validator", versions["dicom_validator"]),
                ("DICOM edition read by dicom-validator", versions["edition"]),
                *(
                    (f"SHA-256 of {name}", f"`{digest}`")
                    for name, digest in versions["docbook_sha256"].items()
                ),
            ],
        ),
        "",
        "## Instances",
        "",
        f"{document['pairs']} released instances compared; "
        f"{document['unpaired']} inputs without an output of their own.",
        "",
        _table(("SOP Class", "Instances"), list(document["sop_classes"].items())),
        "",
        "## Findings by validator",
        "",
        "Counts of findings, by severity, in the inputs and in the outputs, "
        "and of the inputs' findings that the outputs no longer give. "
        "`dcentvfy` compares the instances of each patient together.",
        "",
    ]
    for name, tally in tallies.items():
        lines += [
            f"### {name}",
            "",
            _table(("Status", "Pairs or patients"), list(tally["statuses"].items())),
            "",
            _table(
                ("Severity", "In inputs", "In outputs"),
                [
                    (
                        severity,
                        tally["input_findings"].get(severity, 0),
                        tally["output_findings"].get(severity, 0),
                    )
                    for severity in sorted(
                        {*tally["input_findings"], *tally["output_findings"]}
                    )
                ],
            ),
            "",
            f"Resolved: {tally['resolved']}.",
            "",
        ]
    lines += _introduced(introduced, document["known_differences"])
    return "\n".join(lines).rstrip("\n") + "\n"


def _introduced(
    introduced: list[Mapping[str, object]], known: list[Mapping[str, object]]
) -> list[str]:
    """Render the introduced findings, and the known differences they match."""
    lines = ["## Introduced findings", ""]
    for outcome, heading in _OUTCOMES:
        rows = [row for row in introduced if row["outcome"] == outcome]
        lines += [f"### {heading}", ""]
        header = ["Validator", "Severity", "Attribute", "Message", "Module or entity"]
        if outcome == "explained":
            header.append("Known difference")
        header += ["Files", "Occurrences", "SOP Classes"]
        lines += _rows_or_none(
            header,
            [
                (
                    row["validator"],
                    row["severity"],
                    attribute(str(row["path"])),
                    row["message"],
                    row["context"],
                    *((row["difference"],) if outcome == "explained" else ()),
                    row["files"],
                    row["occurrences"],
                    ", ".join(row["sop_classes"]),  # type: ignore[arg-type]
                )
                for row in rows
            ],
        )
        lines.append("")
    matched: dict[object, list[Mapping[str, object]]] = {}
    for row in introduced:
        if row["outcome"] == "explained":
            matched.setdefault(row["difference"], []).append(row)
    lines += [
        "## Known differences",
        "",
        "Each explained finding matches one of these entries. Those of the "
        "category `engine` are defects of the engine's output, recorded until "
        "they are fixed.",
        "",
    ]
    lines += _rows_or_none(
        ("Number", "Category", "Validator", "Message", "Kinds", "Files", "Reason"),
        [
            (
                difference["number"],
                difference["category"],
                difference["validator"],
                difference["message"],
                len(matched.get(difference["number"], [])),
                max(
                    (
                        int(row["files"])
                        for row in matched.get(difference["number"], [])
                    ),
                    default=0,
                ),
                difference["reason"],
            )
            for difference in sorted(
                known, key=lambda d: (d["category"] != "engine", d["number"])
            )
        ],
    )
    lines.append("")
    return lines


def attribute(path: str) -> str:
    """Return a path of tags with the keyword of its last attribute.

    >>> attribute("(0008,1115)/(0008,1150)")
    '(0008,1115)/(0008,1150) ReferencedSOPClassUID'
    >>> attribute("")
    'none'
    """
    if not path:
        return "none"
    found = _TAG.match(path.rpartition("/")[2])
    if found is None:
        return path
    keyword = pydicom.datadict.keyword_for_tag(int(found.group(1) + found.group(2), 16))
    return f"{path} {keyword}" if keyword else path


def _rows_or_none(header: Sequence[str], rows: list[Sequence[object]]) -> list[str]:
    return [_table(header, rows)] if rows else ["None."]


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def _cell(value: object) -> str:
    if value is None or value == "":
        return "none"
    text = " ".join(str(value).split())
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
