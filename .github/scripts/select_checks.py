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

"""Select affected PR checks; uncertainty always requests full validation.

Diff the tested merge tree against its base parent, with rename detection off,
so deletions and both sides of a rename remain visible. Two checkout generations
suffice and there is no API file-count limit. Main, release and manual runs keep
full validation; only known PR inputs are eligible for reduced coverage.
"""

import json
import os
import re
import subprocess
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

OUTPUTS = (
    "run-python",
    "run-docs",
    "run-integration",
    "run-database",
    "run-scripts",
    "run-full-matrix",
    "run-dependency-audit",
    "run-python-security",
    "run-workflow-audit",
)
# Only main and the full-test label widen the unit tests to every OS and
# Python version; no changed path does.
PATH_SELECTABLE = tuple(output for output in OUTPUTS if output != "run-full-matrix")
# Labels compare case-insensitively, as GitHub's contains() does.
FULL_TEST_LABEL = "full-test"
DATABASE_LABEL = "database"

PACKAGE_ROOT = "lib/pymedphys/"
TESTS_ROOT = "lib/pymedphys/tests/"
# The repository-root docs is a symlink to this directory, so git reports only
# the link itself, which is not documentation and selects every check.
DOC_ROOT = "lib/pymedphys/docs/"
# Only prose and rendered assets are exempt from Python checks. A Python file,
# configuration file or new file type in the docs directory remains executable
# input until its consumers have been reviewed.
DOC_SUFFIXES = frozenset(
    {
        ".md",
        ".rst",
        ".ipynb",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".gif",
        ".pdf",
        ".css",
        ".html",
        ".bib",
    }
)
ROOT_DOCS = frozenset(
    {
        "README.rst",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CLAUDE.md",
        "AGENTS.md",
        "SECURITY.md",
    }
)
# Shared imports, fixtures and data access can affect database tests.
SHARED_PREFIXES = (
    "lib/pymedphys/_imports/",
    "lib/pymedphys/_data/",
    "lib/pymedphys/_utilities/",
    "lib/pymedphys/_base/",
)
# Blob modes of ordinary files; 000000 marks the absent side of an addition or
# a deletion. A symlink (120000) or submodule (160000) can stand in for any
# content, so its name says nothing about which checks it affects.
REGULAR_MODES = frozenset({"000000", "100644", "100755"})
RAW_RECORD = re.compile(rb":([0-7]{6}) ([0-7]{6}) [0-9a-f]+ [0-9a-f]+ [A-Z]")
# Policies under which one unrecognised path selects every path-selectable check.
FALLBACK_POLICIES = frozenset({"unclassified input", "symlink or submodule"})

Git = Callable[[list[str]], bytes]


class ChangedPath(NamedTuple):
    """A path in the merge diff; symlinks and submodules are not regular."""

    name: str
    regular: bool = True


class Reason(NamedTuple):
    """Why an output is selected: a policy and, when a path selected it, the path."""

    policy: str
    path: str | None = None


def classify(change: ChangedPath) -> str:
    """Return "docs", "python", "unclassified" or "link" for one changed path."""
    if not change.regular:
        return "link"
    path = PurePosixPath(change.name)
    if change.name in ROOT_DOCS or (
        change.name.startswith(DOC_ROOT) and path.suffix in DOC_SUFFIXES
    ):
        return "docs"
    if change.name.startswith(PACKAGE_ROOT) and path.suffix == ".py":
        return "python"
    return "unclassified"


def _affects_database(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        any("mosaiq" in part or "database" in part for part in path.parts)
        or path.name == "conftest.py"
        or name.startswith(SHARED_PREFIXES)
        or path.parent == PurePosixPath("lib/pymedphys")
    )


def explain_checks(
    changes: Iterable[str | ChangedPath] | None,
    *,
    event_name: str = "pull_request",
    labels: Collection[str] = (),
) -> dict[str, Reason | None]:
    """Return why each output is selected, or None for each skipped output."""
    reasons: dict[str, Reason | None] = dict.fromkeys(OUTPUTS, None)

    def select(outputs: Iterable[str], reason: Reason) -> None:
        for output in outputs:
            if reasons[output] is None:
                reasons[output] = reason

    folded = {label.casefold() for label in labels}
    if event_name != "pull_request":
        select(OUTPUTS, Reason(f"{event_name} event"))
        # ReadTheDocs publishes main independently; retain the existing policy.
        if event_name == "push":
            reasons["run-docs"] = None
        return reasons
    if FULL_TEST_LABEL in folded:
        select(OUTPUTS, Reason("full-test label"))
        return reasons
    if changes is None:
        select(PATH_SELECTABLE, Reason("unverified merge diff"))
        return reasons
    if DATABASE_LABEL in folded:
        select(["run-database"], Reason("database label"))

    for item in changes:
        change = ChangedPath(item) if isinstance(item, str) else item
        kind = classify(change)
        if kind == "docs":
            select(["run-docs"], Reason("documentation", change.name))
        elif kind == "python":
            reason = Reason("package Python", change.name)
            # Online audits have changing external inputs even when the lockfile
            # and workflows are untouched. Retain their existing PR cadence.
            select(
                (
                    "run-python",
                    "run-python-security",
                    "run-dependency-audit",
                    "run-workflow-audit",
                ),
                reason,
            )
            # Autodoc and notebooks import package modules, never the tests.
            if not change.name.startswith(TESTS_ROOT):
                select(["run-docs"], reason)
            if _affects_database(change.name):
                select(["run-database"], reason)
        else:
            # Dependencies, non-Python fixtures, build/CI configuration, links
            # and unknown paths can affect any check. A deny-list of extensions
            # would silently miss new consumers and is deliberately avoided.
            policy = "symlink or submodule" if kind == "link" else "unclassified input"
            select(PATH_SELECTABLE, Reason(policy, change.name))
    return reasons


def select_checks(
    changes: Iterable[str | ChangedPath] | None,
    *,
    event_name: str = "pull_request",
    labels: Collection[str] = (),
) -> dict[str, bool]:
    """Return explicit booleans for every output, never an incomplete selection."""
    reasons = explain_checks(changes, event_name=event_name, labels=labels)
    return {output: reason is not None for output, reason in reasons.items()}


def parse_raw_diff(raw: bytes) -> list[ChangedPath]:
    """Parse ``git diff --raw -z --no-renames``: each record, then its path."""
    fields = raw.split(b"\0")
    if fields[-1] != b"":
        raise ValueError("The raw diff does not end with a NUL.")
    fields.pop()
    if len(fields) % 2:
        raise ValueError("A raw diff record has no path.")
    changes: list[ChangedPath] = []
    for record, name in zip(fields[::2], fields[1::2]):
        match = RAW_RECORD.fullmatch(record)
        if match is None or not name:
            raise ValueError(f"Unexpected raw diff record {record!r}.")
        modes = {match[1].decode(), match[2].decode()}
        changes.append(ChangedPath(name.decode("utf-8"), modes <= REGULAR_MODES))
    return changes


def changed_paths(
    event: Mapping[str, Any], *, git: Git = subprocess.check_output
) -> list[ChangedPath] | None:
    """Return every changed path, or None if the tested merge is unprovable."""
    try:
        pr = event["pull_request"]
        expected = [pr["base"]["sha"], pr["head"]["sha"]]
        parents = git(["git", "show", "-s", "--format=%P", "HEAD"]).decode().split()
        if parents != expected:
            return None
        raw = git(
            [
                "git",
                "diff",
                "--raw",
                "--no-renames",
                "--no-abbrev",
                "--ignore-submodules=none",
                "-z",
                "HEAD^1",
                "HEAD",
                "--",
            ]
        )
        # NUL delimiters preserve spaces, newlines and shell metacharacters.
        return parse_raw_diff(raw)
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.CalledProcessError,
    ):
        return None


def _code(text: str) -> str:
    """Show untrusted text as inline code that cannot break a table row."""
    # JSON escapes quotes, control characters and every non-ASCII character,
    # including bidirectional overrides that could disguise a path.
    text = json.dumps(text)[1:-1].replace("|", "\\|")
    fence = "`" * (max(map(len, re.findall("`+", text)), default=0) + 1)
    return f"{fence} {text} {fence}"


def _describe(reason: Reason | None) -> str:
    if reason is None:
        return ""
    if reason.path is None:
        return reason.policy
    return f"{reason.policy} {_code(reason.path)}"


def render_summary(
    reasons: Mapping[str, Reason | None], changes: Sequence[ChangedPath] | None
) -> str:
    """Return the step summary, including the path behind any fallback."""
    lines = [
        "## Check selection",
        "",
        "| Check | Selected | Reason |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {output} | {'yes' if reason else 'no'} | {_describe(reason)} |"
        for output, reason in reasons.items()
    ]
    policies = {reason.policy for reason in reasons.values() if reason is not None}
    if "unverified merge diff" in policies:
        lines += [
            "",
            "The merge diff could not be verified, so every check that a changed "
            "path can select runs.",
        ]
    elif policies & FALLBACK_POLICIES and changes is not None:
        fallback = [c for c in changes if classify(c) in {"unclassified", "link"}]
        first = fallback[0]
        what = (
            "a symlink or submodule"
            if not first.regular
            else "not a recognised documentation or package Python input"
        )
        count = len(fallback) - 1
        others = (
            f" {count} more changed {'path is' if count == 1 else 'paths are'} "
            "also unclassified."
            if count
            else ""
        )
        lines += [
            "",
            f"Fallback: {_code(first.name)} is {what}, so it selects every check "
            f"that a changed path can select.{others}",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    changes = changed_paths(event) if event_name == "pull_request" else None
    labels = [
        label["name"] for label in event.get("pull_request", {}).get("labels", [])
    ]
    reasons = explain_checks(changes, event_name=event_name, labels=labels)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for name, reason in reasons.items():
            output.write(f"{name}={str(reason is not None).lower()}\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(render_summary(reasons, changes))


if __name__ == "__main__":
    main()
