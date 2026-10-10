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

"""Render the MIDI benchmark's results (D-018) as CommonMark.

:func:`render_markdown` writes ``benchmark.md`` from the record that
:func:`~pymedphys._dicom.deidentify.midi_benchmark.score` makes, which holds
no value from the test data set's files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence


def render_markdown(document: Mapping[str, object]) -> str:
    """Render a benchmark's results as CommonMark."""
    versions = document["versions"]
    coverage = document["coverage"]
    assert isinstance(versions, Mapping) and isinstance(coverage, Mapping)
    lines = [
        "# MIDI benchmark results",
        "",
        f"Format `{document['format']}`. Development results: the NCI "
        "validation script's own results, from the mapping files that the "
        "run wrote, are the published figures (D-018).",
        "",
        "## Versions",
        "",
        "| Item | Version |",
        "| --- | --- |",
        *(f"| {name} | {_cell(value)} |" for name, value in versions.items()),
        "",
        "## Headline",
        "",
        "Every check of the answer key, wherever its instance ended up. Checks "
        "of instances that the run did not release, or that the input did not "
        "hold, are outcomes of their own, neither passed nor failed, so that "
        "no check leaves the total.",
        "",
        _headline(document["headline"]),
        "",
        "## Supported coverage",
        "",
        "Answer-key instances by where they ended up:",
        "",
        _table(
            ("Modality", *coverage["instances"]),
            [
                (modality, *by.values())
                for modality, by in coverage["by_modality"].items()
            ]
            + [("All", *coverage["instances"].values())],
        ),
        "",
    ]
    reasons = coverage["withheld_reasons"]
    if reasons:
        lines += [
            "Reasons the run gave for withheld instances:",
            "",
            _table(("Reason", "Times given"), list(reasons.items())),
            "",
        ]
    lines += [
        "Instances that the run did not release, by where they ended up, the "
        "reasons the run gave, their SOP Class, and their transfer syntax:",
        "",
    ]
    lines += _rows_or_none(
        (
            "Where",
            "Reasons",
            "SOP Class",
            "Transfer syntax",
            "Instances",
            "Checks",
        ),
        [
            (
                row["context"],
                row["reasons"],
                row["sop_class"],
                row["transfer_syntax"],
                row["instances"],
                row["checks"],
            )
            for row in coverage["not_released"]
        ],
    )
    lines += [
        "",
        "## Results by answer-key category",
        "",
        "Checks of released instances passed, failed, failed by a deliberate "
        "difference, or were not evaluated; checks of other instances are "
        "counted where those instances ended up, and not scored.",
        "",
        _table(
            (
                "Category",
                "Passed",
                "Failed",
                "Deliberate",
                "Not evaluated",
                "Withheld",
                "Outside coverage",
                "Not in input",
            ),
            [
                (
                    "unknown"
                    if row["code"] is None
                    else f"{row['family']} {row['code']}",
                    row["passed"],
                    row["failed"],
                    row["deliberate"],
                    row["not_evaluated"],
                    row["withheld"],
                    row["outside_coverage"],
                    row["not_in_input"],
                )
                for row in document["categories"]
            ]
            + [
                (
                    "All",
                    *(
                        document["headline"][field]  # type: ignore[index]
                        for field in _OUTCOMES
                    ),
                )
            ],
        ),
        "",
        "## Deliberate differences",
        "",
        "Checks that asked for an attribute to be kept, where the policy "
        "removes or replaces it:",
        "",
    ]
    lines += _rows_or_none(
        ("Category", "Action", "Attribute", "Policy action", "Checks"),
        [
            (
                row["category"],
                row["action"],
                row["attribute"],
                row["policy_action"],
                row["checks"],
            )
            for row in document["deliberate_differences"]
        ],
    )
    lines += ["", "## Findings", "", "Every other failed check:", ""]
    lines += _rows_or_none(
        ("Category", "Action", "Attribute", "Checks"),
        [
            (row["category"], row["action"], row["attribute"], row["checks"])
            for row in document["findings"]
        ],
    )
    return "\n".join(lines) + "\n"


# The fields of CategoryCounts, in their order, with their headline names.
_OUTCOMES = {
    "passed": "Passed",
    "failed": "Failed: findings",
    "deliberate": "Failed: deliberate differences",
    "not_evaluated": "Not evaluated",
    "withheld": "Not released: withheld",
    "outside_coverage": "Not released: outside coverage",
    "not_in_input": "Not in the input",
}


def _headline(headline: object) -> str:
    assert isinstance(headline, Mapping)
    total = headline["checks"]

    def share(number: int) -> str:
        return f"{100 * number / total:.1f}%" if total else "none"

    return _table(
        ("Outcome", "Checks", "Share"),
        [
            *(
                (name, headline[field], share(headline[field]))
                for field, name in _OUTCOMES.items()
            ),
            ("All checks", total, share(total)),
        ],
    )


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
    if value is None:
        return "none"
    return " ".join(str(value).split()).replace("|", "\\|")
