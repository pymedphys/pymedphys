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

"""Generate the requirements-to-tests matrix from the requirements register.

The matrix lists each requirement of ``requirements.toml`` with its status,
milestone, decisions, modules, and the tests that trace it, and lists the
exclusions with the reason for each (D-018). Given pytest's JUnit XML reports,
it also gives each traced test's outcome, and each requirement passes only
when every test that traces it passed in full.
"""

from __future__ import annotations

import collections
import dataclasses
import pathlib
import re

# The reports are written by the caller's own pytest runs, and ElementTree
# expands no external entities.
import xml.etree.ElementTree as ElementTree  # nosec B405
from collections.abc import Iterable, Mapping

from .requirements import STATUSES, Requirement, RequirementsRegister

EXCLUDED = ("out-of-scope", "not-applicable")
REMAINING = ("planned", "partial")


class TraceabilityError(ValueError):
    """A JUnit XML report is missing or malformed."""


@dataclasses.dataclass(frozen=True)
class TestResult:
    """The outcome of a traced test in the given reports.

    Attributes
    ----------
    counts : tuple of int
        The number of the test's cases, across every report, that passed,
        failed (including errors), and were skipped (including expected
        failures).
    """

    __test__ = False  # Not a pytest test class, despite its name.

    counts: tuple[int, int, int]

    @property
    def outcome(self) -> str:
        """``"failed"`` if any case failed, ``"not run"`` if none ran,
        ``"skipped"`` if any was skipped, and ``"passed"`` otherwise."""
        passed, failed, skipped = self.counts
        if failed:
            return "failed"
        if not passed + skipped:
            return "not run"
        if skipped:
            return "skipped"
        return "passed"


@dataclasses.dataclass(frozen=True)
class TracedTest:
    """A test that a requirement cites, and its result if reports were given."""

    __test__ = False  # Not a pytest test class, despite its name.

    node_id: str
    result: TestResult | None


@dataclasses.dataclass(frozen=True)
class MatrixRow:
    """A requirement and its traced tests."""

    requirement: Requirement
    tests: tuple[TracedTest, ...]

    @property
    def verdict(self) -> str | None:
        """For a requirement with tests, given reports: ``"failed"`` if any
        test failed, ``"incomplete"`` if any was skipped or not run, and
        ``"passed"`` otherwise. None without reports or tests."""
        outcomes = {test.result.outcome for test in self.tests if test.result}
        if not outcomes:
            return None
        if "failed" in outcomes:
            return "failed"
        if outcomes != {"passed"}:
            return "incomplete"
        return "passed"


@dataclasses.dataclass(frozen=True)
class TraceabilityMatrix:
    """The requirements-to-tests matrix.

    Attributes
    ----------
    register : RequirementsRegister
    rows : tuple of MatrixRow
        One for each requirement, in the register's order.
    reports : tuple of str
        The file names of the JUnit XML reports the results come from.
    """

    register: RequirementsRegister
    rows: tuple[MatrixRow, ...]
    reports: tuple[str, ...]

    def problems(self) -> tuple[str, ...]:
        """Each traced test that failed, was skipped, or did not run.

        Returns
        -------
        tuple of str
            Such as ``"PS3.15-E.1.1-01: tests/x/test_y.py::test_z failed"``,
            in the register's order. Empty without reports.
        """
        return tuple(
            f"{row.requirement.id}: {test.node_id} {test.result.outcome}"
            for row in self.rows
            for test in row.tests
            if test.result and test.result.outcome != "passed"
        )


def exclusions(register: RequirementsRegister) -> tuple[Requirement, ...]:
    """Return the requirements that are out of scope or not applicable.

    Each has a note saying why, which the register's loader requires.
    """
    return tuple(entry for entry in register.requirements if entry.status in EXCLUDED)


def _read_report(path: pathlib.Path) -> collections.Counter[tuple[str, str, str]]:
    """Count a JUnit XML report's cases by class name, name, and outcome."""
    try:
        root = ElementTree.parse(path).getroot()  # nosec B314
    except (OSError, ElementTree.ParseError) as error:
        raise TraceabilityError(
            f"{path.name} could not be read as a JUnit XML report"
        ) from error
    if root.tag not in ("testsuites", "testsuite"):
        raise TraceabilityError(f"{path.name} is not a JUnit XML report")
    cases: collections.Counter[tuple[str, str, str]] = collections.Counter()
    for case in root.iter("testcase"):
        classname, name = case.get("classname"), case.get("name")
        if not (classname and name):
            raise TraceabilityError(
                f"{path.name} has a test case without a class name and a name"
            )
        children = {child.tag for child in case}
        if children & {"failure", "error"}:
            outcome = "failed"
        elif "skipped" in children:
            outcome = "skipped"
        else:
            outcome = "passed"
        cases[classname, name, outcome] += 1
    return cases


def _matches(node_id: str, classname: str, name: str) -> bool:
    """Return whether a JUnit test case is a case of the test ``node_id``.

    pytest names a case's class by its module's dotted path from the rootdir,
    then any classes, so the node id's path must match a whole trailing part
    of it; a parametrised case's name adds its parameters in brackets.
    """
    path, *classes, function = node_id.split("::")
    expected = ".".join([path.removesuffix(".py").replace("/", "."), *classes])
    return (classname == expected or classname.endswith("." + expected)) and (
        name == function or name.startswith(function + "[")
    )


def _result(node_id: str, cases: Mapping[tuple[str, str, str], int]) -> TestResult:
    counts = dict.fromkeys(("passed", "failed", "skipped"), 0)
    for (classname, name, outcome), count in cases.items():
        if _matches(node_id, classname, name):
            counts[outcome] += count
    return TestResult(counts=(counts["passed"], counts["failed"], counts["skipped"]))


def build_matrix(
    register: RequirementsRegister, reports: Iterable[pathlib.Path] = ()
) -> TraceabilityMatrix:
    """Build the requirements-to-tests matrix.

    Parameters
    ----------
    register : RequirementsRegister
        From :func:`pymedphys._dicom.deidentify.requirements.load_requirements`.
    reports : iterable of pathlib.Path, optional
        pytest JUnit XML reports (``pytest --junitxml``), such as one for each
        environment that continuous integration tests. A traced test fails if
        any of its cases failed in any report.

    Returns
    -------
    TraceabilityMatrix

    Raises
    ------
    TraceabilityError
        If a report cannot be read or is not a JUnit XML report.
    """
    reports = tuple(reports)
    cases: collections.Counter[tuple[str, str, str]] = collections.Counter()
    for path in reports:
        cases.update(_read_report(path))
    rows = tuple(
        MatrixRow(
            requirement=entry,
            tests=tuple(
                TracedTest(
                    node_id=node_id,
                    result=_result(node_id, cases) if reports else None,
                )
                for node_id in entry.tests
            ),
        )
        for entry in register.requirements
    )
    return TraceabilityMatrix(
        register=register,
        rows=rows,
        reports=tuple(path.name for path in reports),
    )


def _cell(text: str | None) -> str:
    """Return text for a Markdown table cell: on one line, with pipes escaped."""
    return " ".join((text or "").split()).replace("|", "\\|")


def _label(entry: Requirement) -> str:
    return f"[{entry.id}]({entry.url})" if entry.url else entry.id


def _table(header: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _fenced(text: str) -> list[str]:
    """Fence text verbatim, with a fence longer than any backtick run in it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}text", text, fence]


def _outcome(result: TestResult) -> str:
    parts = [
        f"{count} {label}"
        for count, label in zip(result.counts, ("passed", "failed", "skipped"))
        if count
    ]
    return result.outcome + (f" ({', '.join(parts)})" if parts else "")


def _summary(matrix: TraceabilityMatrix) -> list[str]:
    entries = [row.requirement for row in matrix.rows]
    by_status = collections.Counter((entry.status, entry.source) for entry in entries)
    rows = [
        (
            status,
            str(by_status[status, "PS3.15"]),
            str(by_status[status, "MIDI"]),
            str(by_status[status, "PS3.15"] + by_status[status, "MIDI"]),
        )
        for status in STATUSES
    ]
    sources = collections.Counter(entry.source for entry in entries)
    rows.append(
        ("Total", str(sources["PS3.15"]), str(sources["MIDI"]), str(len(entries)))
    )
    lines = ["## Summary", "", *_table(("Status", "PS3.15", "MIDI", "Total"), rows)]
    if matrix.reports:
        verdicts = collections.Counter(row.verdict for row in matrix.rows)
        lines += [
            "",
            *_table(
                ("Verdict", "Requirements"),
                [
                    (verdict, str(verdicts[verdict]))
                    for verdict in ("passed", "failed", "incomplete")
                ]
                + [("no traced tests", str(verdicts[None]))],
            ),
        ]
    return lines


def _overview(matrix: TraceabilityMatrix) -> list[str]:
    header: tuple[str, ...] = (
        "Requirement",
        "Status",
        "Milestone",
        "Decisions",
        "Tests",
    )
    rows = []
    for row in matrix.rows:
        entry = row.requirement
        cells: tuple[str, ...] = (
            _label(entry),
            entry.status,
            entry.milestone or "",
            ", ".join(entry.decisions),
            str(len(row.tests)),
        )
        if matrix.reports:
            cells += (row.verdict or "",)
        rows.append(cells)
    if matrix.reports:
        header += ("Verdict",)
    return ["## Requirements", "", *_table(header, rows)]


def _exclusions(matrix: TraceabilityMatrix) -> list[str]:
    rows = [
        (_label(entry), entry.status, _cell(entry.note))
        for entry in exclusions(matrix.register)
    ]
    return ["## Exclusions", "", *_table(("Requirement", "Status", "Reason"), rows)]


def _remaining(matrix: TraceabilityMatrix) -> list[str]:
    rows = [
        (_label(entry), entry.status, entry.milestone or "", _cell(entry.note))
        for entry in matrix.register.requirements
        if entry.status in REMAINING
    ]
    header = ("Requirement", "Status", "Milestone", "Note")
    return ["## Remaining work", "", *_table(header, rows)]


def _details(row: MatrixRow) -> list[str]:
    entry = row.requirement
    source = (
        f"PS3.15 {entry.section}, [paragraph]({entry.url})"
        if entry.url
        else f"MIDI report §{entry.section}"
    )
    status = entry.status + (
        f", remaining work in {entry.milestone}" if entry.milestone else ""
    )
    lines = [
        f"### {entry.id}",
        "",
        f"Source: {source}. Status: {status}.",
        "",
        *_fenced(entry.text),
    ]
    if entry.decisions:
        lines += ["", f"Decisions: {', '.join(entry.decisions)}."]
    if entry.implementation:
        lines += ["", "Implementation:", ""]
        lines += [f"- `{path}`" for path in entry.implementation]
    if row.tests:
        lines += ["", "Tests:", ""]
        lines += [
            f"- `{test.node_id}`"
            + (f": {_outcome(test.result)}" if test.result else "")
            for test in row.tests
        ]
    if entry.note:
        lines += ["", "Note: " + " ".join(entry.note.split())]
    return lines


def render_markdown(matrix: TraceabilityMatrix) -> str:
    """Render the matrix as a CommonMark document with GitHub tables.

    The document depends only on the register and the reports, so the same
    inputs give the same bytes.
    """
    register = matrix.register
    if matrix.reports:
        results = (
            "Test results are from "
            + ", ".join(f"`{name}`" for name in matrix.reports)
            + ". A requirement passes only when every case of every test that "
            "traces it passed; a skipped or missing case leaves it incomplete."
        )
    else:
        results = (
            "No test results were given, so the matrix lists the tests that "
            "trace each requirement without their outcomes."
        )
    lines = [
        "# DICOM de-identification requirements-to-tests matrix",
        "",
        "Generated from the PyMedPhys requirements register, "
        "`pymedphys/_dicom/deidentify/requirements.toml`, which records each "
        f"paragraph of DICOM PS3.15 Annex E ({register.edition}) that contains "
        '"shall" and each best practice of the MIDI Task Group report. '
        f"PS3.15 text is reproduced verbatim from {register.acknowledgement}. "
        f"MIDI report: {register.midi_report}.",
        "",
        results,
        "",
        *_summary(matrix),
        "",
        *_overview(matrix),
        "",
        *_exclusions(matrix),
        "",
        *_remaining(matrix),
        "",
        "## Details",
    ]
    for row in matrix.rows:
        lines += ["", *_details(row)]
    return "\n".join(lines) + "\n"
