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

"""Load the requirements register for the de-identification engine.

``requirements.toml`` records each normative paragraph of DICOM PS3.15 Annex E
that contains "shall", and each best practice of the MIDI Task Group report,
with its status and what satisfies it. It is curated by hand, so this loader
checks its structure; the tests check that the decisions and paths it cites
exist and that pytest collects the tests that cite it. The design document's
"Requirements register" section describes the fields and statuses.

A test cites the requirements it shows are met with a marker,
``@pytest.mark.deid_requirement("PS3.15-E.1.1-01")``, on the test function
or on its ``Test`` class, rather than the register listing the test, so that
pull requests that add tests to the same requirement change different files.
:func:`cited_tests` reads these markers from the tests' source without
importing them. A note may be written one sentence per line, and its lines
are joined with spaces, for the same reason.
"""

from __future__ import annotations

import ast
import collections
import dataclasses
import pathlib
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import TypeGuard

from pymedphys._imports import tomlkit

SCHEMA = "pymedphys-deid-requirements/2"

REGISTER_PATH = pathlib.Path(__file__).resolve().parent / "requirements.toml"
# The pymedphys package, whose tests directory holds the citing tests, and
# relative to which a test's node id is given.
LIBRARY_ROOT = pathlib.Path(__file__).resolve().parents[2]
# The pytest marker with which a test cites requirements.
MARKER = "deid_requirement"

# In the order work progresses, then the two kinds of exclusion.
STATUSES = ("planned", "partial", "implemented", "out-of-scope", "not-applicable")
MILESTONES = ("M1", "M2", "M3", "M4", "M5", "M6", "M7")

# A paragraph of PS3.15 Annex E, numbered within its section, such as
# "PS3.15-E.1.1-01", or one of the 18 best practices of MIDI section 1.6.
_ID_PATTERN = re.compile(
    r"(?:PS3\.15-(?P<section>E(?:\.[0-9]+)*)-[0-9]{2}|MIDI-BP-(?:0[1-9]|1[0-8]))"
)
# The paragraph's anchor on the current edition's chunked HTML pages.
_URL_PATTERN = re.compile(
    r"https://dicom\.nema\.org/medical/dicom/current/output/chtml/part15/"
    r"(?:chapter_E|sect_E(?:\.[0-9]+)+)\.html"
    r"#para_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_DECISION_PATTERN = re.compile(r"D-[0-9]{3}")
# Paths within the pymedphys package, and pytest node ids of its tests under
# pytest's default naming rules: test functions, optionally in Test classes.
_PATH_PATTERN = re.compile(
    r"(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
)
_TEST_PATTERN = re.compile(
    r"tests/(?:[A-Za-z0-9_]+/)*test_[A-Za-z0-9_]+\.py(?:::Test\w*)*::test\w*"
)

_REQUIRED = frozenset({"id", "text", "status"})
_FIELDS = _REQUIRED | {
    "url",
    "milestone",
    "decisions",
    "implementation",
    "note",
}


class RequirementsError(ValueError):
    """The requirements register is missing or malformed."""


@dataclasses.dataclass(frozen=True)
class Requirement:
    """One requirement or best practice, and how PyMedPhys satisfies it.

    Attributes
    ----------
    id : str
        A stable identifier that is never reused, such as ``"PS3.15-E.1.1-01"``
        or ``"MIDI-BP-06"``.
    source : str
        ``"PS3.15"`` or ``"MIDI"``.
    section : str
        The section of the source, such as ``"E.1.1"``, or ``"1.6"`` for the
        MIDI best practices.
    url : str or None
        For PS3.15, the paragraph on the current edition's web pages.
    text : str
        For PS3.15, the paragraph verbatim, with any list it introduces. For
        MIDI, a summary of the best practice in PyMedPhys's words.
    status : str
        One of :data:`STATUSES`.
    milestone : str or None
        For planned and partial requirements, the milestone of the design
        document's roadmap that delivers the remaining work.
    decisions : tuple of str
        The design decisions that address the requirement, such as
        ``"D-003"``.
    implementation : tuple of str
        For partial and implemented requirements, the modules that satisfy
        it, relative to the pymedphys package.
    tests : tuple of str
        For partial and implemented requirements, the pytest node ids of the
        tests that cite it with the ``deid_requirement`` marker and so show
        it is met, relative to the pymedphys package, such as
        ``tests/x/test_y.py::test_z`` or ``tests/x/test_y.py::TestZ::test_z``,
        in the order of their files and then of their definitions. An id for
        a parametrised test covers each of its cases.
    note : str or None
        Context for the status, its lines joined with spaces. Required for
        exclusions, to say why.
    """

    id: str
    source: str
    section: str
    url: str | None
    text: str
    status: str
    milestone: str | None
    decisions: tuple[str, ...]
    implementation: tuple[str, ...]
    tests: tuple[str, ...]
    note: str | None


@dataclasses.dataclass(frozen=True)
class RequirementsRegister:
    """The requirements register.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.15 whose text the register records, which
        matches the generated tables.
    acknowledgement : str
        The copyright attribution for that text, such as
        ``"DICOM PS3.15 2026d, © NEMA"``.
    midi_report : str
        The citation of the MIDI Task Group report.
    requirements : tuple of Requirement
        In the register's order.
    """

    edition: str
    acknowledgement: str
    midi_report: str
    requirements: tuple[Requirement, ...]


def _is_text(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _texts(value: object, pattern: re.Pattern[str]) -> bool:
    """Return whether ``value`` is a list of distinct strings matching ``pattern``."""
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and pattern.fullmatch(item) for item in value)
        and len(set(value)) == len(value)
    )


def _source_problem(entry: dict, source: str) -> str | None:
    """Return what is wrong with a requirement's url and text, if anything."""
    url = entry.get("url")
    if source == "PS3.15" and url is None:
        return "lacks a url to its paragraph"
    if source == "MIDI" and url is not None:
        return "has a url, which only PS3.15 requirements have"
    if url is not None and not (isinstance(url, str) and _URL_PATTERN.fullmatch(url)):
        return "has a url that is not a paragraph of PS3.15 on dicom.nema.org"
    if not _is_text(entry["text"]):
        return "has text that is not non-empty"
    if source == "PS3.15" and not re.search(r"\bshall\b", entry["text"]):
        return "has text that does not contain 'shall'"
    return None


def _status_problem(entry: dict, _source: str) -> str | None:
    """Return what is wrong with a requirement's status and milestone, if anything."""
    status = entry["status"]
    if status not in STATUSES:
        return "has a status that is not one of " + ", ".join(STATUSES)
    milestone = entry.get("milestone")
    if status in ("planned", "partial"):
        if milestone is None:
            return f"is {status} without a milestone"
        if milestone not in MILESTONES:
            return "has a milestone that is not one of M1 to M7"
    elif milestone is not None:
        return f"is {status} with a milestone"
    return None


def _trace_problem(entry: dict, _source: str) -> str | None:
    """Return what is wrong with what a requirement cites, if anything."""
    if not _texts(entry.get("decisions", []), _DECISION_PATTERN):
        return "has decisions that are not distinct D-NNN identifiers"
    implementation = entry.get("implementation", [])
    tests = entry.get("tests", [])
    if not _texts(implementation, _PATH_PATTERN):
        return "has implementation that is not distinct paths within pymedphys"
    if not _texts(tests, _TEST_PATTERN):
        return (
            "has tests that are not pytest node ids such as tests/x/test_y.py::test_z"
        )
    status = entry["status"]
    if status in ("partial", "implemented"):
        if not (implementation and tests):
            return f"is {status} without implementation or tests"
    elif implementation or tests:
        return f"is {status} with implementation or tests"
    return None


def _note_problem(entry: dict, _source: str) -> str | None:
    """Return what is wrong with a requirement's note, if anything."""
    note = entry.get("note")
    if note is not None and not _is_text(note):
        return "has a note that is not non-empty"
    if entry["status"] in ("out-of-scope", "not-applicable") and note is None:
        return f"is {entry['status']} without a note"
    return None


def _requirement_problem(entry: dict, source: str) -> str | None:
    """Return what is wrong with a requirement, or None if it is valid."""
    for check in (_source_problem, _status_problem, _trace_problem, _note_problem):
        issue = check(entry, source)
        if issue:
            return issue
    return None


def _note(note: str) -> str:
    """Return a note written one sentence per line as one line."""
    return " ".join(line.strip() for line in note.splitlines() if line.strip())


def _requirements(
    name: str, entries: list, tests: Mapping[str, Sequence[str]]
) -> tuple[Requirement, ...]:
    """Return the checked requirements of a register."""
    parsed = []
    ids: set[str] = set()
    urls: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise RequirementsError(f"{name} requirement #{number} is not a table")
        identifier = entry.get("id")
        match = (
            _ID_PATTERN.fullmatch(identifier) if isinstance(identifier, str) else None
        )
        label = identifier if match else f"#{number}"
        if not entry.keys() <= _FIELDS:
            raise RequirementsError(
                f"{name} requirement {label} does not have only the fields "
                + ", ".join(sorted(_FIELDS))
            )
        if not entry.keys() >= _REQUIRED:
            raise RequirementsError(
                f"{name} requirement {label} lacks id, text, or status"
            )
        if match is None:
            raise RequirementsError(
                f"{name} requirement #{number} has an id that is not of the form "
                "PS3.15-E.1.1-01 or MIDI-BP-01 to MIDI-BP-18"
            )
        identifier = match.group(0)
        source = "MIDI" if match.group("section") is None else "PS3.15"
        entry = {**entry, "tests": list(tests.get(identifier, ()))}
        issue = _requirement_problem(entry, source)
        if issue:
            raise RequirementsError(f"{name} requirement {label} {issue}")
        if identifier in ids:
            raise RequirementsError(f"{name} requirement {label} repeats an id")
        if entry.get("url") in urls:
            raise RequirementsError(f"{name} requirement {label} repeats a url")
        ids.add(identifier)
        if "url" in entry:
            urls.add(entry["url"])
        note = entry.get("note")
        parsed.append(
            Requirement(
                id=identifier,
                source=source,
                section=match.group("section") or "1.6",
                url=entry.get("url"),
                text=entry["text"].strip(),
                status=entry["status"],
                milestone=entry.get("milestone"),
                decisions=tuple(entry.get("decisions", [])),
                implementation=tuple(entry.get("implementation", [])),
                tests=tuple(entry.get("tests", [])),
                note=None if note is None else _note(note),
            )
        )
    unknown = sorted(tests.keys() - ids)
    if unknown:
        raise RequirementsError(
            f"a test cites {unknown[0]}, which {name} does not record"
        )
    return tuple(parsed)


def load_requirements(
    path: pathlib.Path | None = None,
    tests: Mapping[str, Sequence[str]] | None = None,
) -> RequirementsRegister:
    """Load and check the requirements register.

    Parameters
    ----------
    path : pathlib.Path, optional
        The register. Defaults to the one shipped with PyMedPhys.
    tests : mapping of str to sequence of str, optional
        The node ids of the tests that cite each requirement, by its id.
        Defaults to :func:`cited_tests` of PyMedPhys's own tests.

    Returns
    -------
    RequirementsRegister

    Raises
    ------
    RequirementsError
        If the register cannot be read or parsed, or an entry has missing,
        unknown, or inconsistent fields, such as an implemented requirement
        without tests or an exclusion without a note, or if a test cites a
        requirement that the register does not record.
    """
    path = path or REGISTER_PATH
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise RequirementsError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise RequirementsError(f"{path.name} is not a {SCHEMA} file")
    edition = document.get("edition")
    if not _is_text(edition):
        raise RequirementsError(f"{path.name} does not name its edition as text")
    acknowledgement = f"DICOM PS3.15 {edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise RequirementsError(f"{path.name} lacks the copyright acknowledgement")
    midi_report = document.get("midi_report")
    if not _is_text(midi_report):
        raise RequirementsError(f"{path.name} does not cite the MIDI report")
    entries = document.get("requirement")
    if not isinstance(entries, list) or not entries:
        raise RequirementsError(f"{path.name} has no requirements")
    return RequirementsRegister(
        edition=edition,
        acknowledgement=acknowledgement,
        midi_report=midi_report,
        requirements=_requirements(
            path.name, entries, cited_tests() if tests is None else tests
        ),
    )


def cited_tests(root: pathlib.Path | None = None) -> dict[str, tuple[str, ...]]:
    """Return the tests that cite each requirement with the marker.

    Reads each ``test_*.py`` file under ``root``'s ``tests`` directory, at any
    depth, without importing it. A citation is a ``deid_requirement`` marker,
    ``@pytest.mark.deid_requirement("MIDI-BP-01", ...)``, decorating a
    function whose name starts with ``test`` at the top level of the file,
    or a class whose name starts with ``Test`` there, which cites the
    requirements for each of its methods whose name starts with ``test``.

    Parameters
    ----------
    root : pathlib.Path, optional
        The directory that node ids are relative to. Defaults to the pymedphys
        package.

    Returns
    -------
    dict of str to tuple of str
        For each cited requirement id, the node ids of the tests that cite
        it, such as ``tests/x/test_y.py::test_z``, in the order of their
        files' paths and then of their definitions.

    Raises
    ------
    RequirementsError
        If a test file cannot be read or parsed, a marker is used other than
        to decorate such a function or class, its arguments are not one or
        more string literals, or a test cites a requirement twice.
    """
    root = root or LIBRARY_ROOT
    cited: dict[str, list[tuple[str, int, str]]] = collections.defaultdict(list)
    for path in sorted((root / "tests").rglob("test_*.py")):
        module = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_bytes(), filename=module)
        except (OSError, SyntaxError, ValueError) as error:
            raise RequirementsError(f"{module} could not be read") from error
        nodes = [node for node in ast.walk(tree) if _is_marker(node)]
        # A called marker's attribute is part of the call.
        called = {id(node.func) for node in nodes if isinstance(node, ast.Call)}
        markers = {id(node) for node in nodes} - called
        used: set[int] = set()
        for name, line, decorators in _tests(tree):
            ids: list[str] = []
            for decorator in decorators:
                if not _is_marker(decorator):
                    continue
                used.add(id(decorator))
                ids.extend(_marker_ids(decorator, module))
            if len(set(ids)) != len(ids):
                raise RequirementsError(
                    f"{module}::{name} cites a requirement more than once"
                )
            for identifier in ids:
                cited[identifier].append((module, line, f"{module}::{name}"))
        if markers - used:
            raise RequirementsError(
                f"{module} uses the {MARKER} marker other than to decorate a "
                "test function or Test class"
            )
    return {
        identifier: tuple(node_id for _, _, node_id in sorted(entries))
        for identifier, entries in sorted(cited.items())
    }


def _is_marker(node: ast.AST) -> bool:
    """Return whether ``node`` is ``pytest.mark.deid_requirement``, called or not."""
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == MARKER
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _marker_ids(decorator: ast.expr, module: str) -> list[str]:
    """Return the requirement ids that a marker decorator cites."""
    arguments = decorator.args if isinstance(decorator, ast.Call) else []
    if (
        not isinstance(decorator, ast.Call)
        or decorator.keywords
        or not arguments
        or not all(
            isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            for argument in arguments
        )
    ):
        raise RequirementsError(
            f"{module} line {decorator.lineno} cites requirements other than "
            "as one or more string literals"
        )
    return [argument.value for argument in arguments]  # type: ignore[attr-defined]


def _tests(tree: ast.Module) -> Iterator[tuple[str, int, list[ast.expr]]]:
    """Yield each test's name, line, and the decorators that apply to it."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                yield node.name, node.lineno, list(node.decorator_list)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and child.name.startswith("test"):
                    yield (
                        f"{node.name}::{child.name}",
                        child.lineno,
                        [*node.decorator_list, *child.decorator_list],
                    )
