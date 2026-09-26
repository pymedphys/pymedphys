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

"""Select the checks a pull request affects; uncertainty widens the selection.

Diff the tested merge tree against its base parent, with rename detection off,
so deletions and both sides of a rename remain visible. Two checkout generations
suffice and there is no API file-count limit. Main, release and manual runs keep
full validation. On pull requests only known inputs skip standard checks, while
the costly integration and database tests and the full unit-test matrix follow
their labels and their own inputs. Links and unverifiable diffs select every
check that a changed path can select.
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
# Integration and database tests are too costly for every PR. Beyond main and
# the labels, they run only for their own inputs, links and unverified diffs.
COST_GATED = ("run-integration", "run-database", "run-full-matrix")
STANDARD = tuple(output for output in OUTPUTS if output not in COST_GATED)
# Labels compare case-insensitively, as GitHub's contains() does.
FULL_TEST_LABEL = "full-test"
DATABASE_LABEL = "database"

PACKAGE_ROOT = "lib/pymedphys/"
TESTS_ROOT = "lib/pymedphys/tests/"
# The repository-root docs is a symlink to this directory, so git reports only
# the link itself, which selects every check that a changed path can select.
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
# Shared imports, fixtures and data access can affect slow and database tests.
SHARED_PREFIXES = (
    "lib/pymedphys/_imports/",
    "lib/pymedphys/_data/",
    "lib/pymedphys/_utilities/",
    "lib/pymedphys/_base/",
)
# Dependency and build metadata: only the integration and database jobs check
# generated-file drift, the wheel build and the locked database drivers.
DEPENDENCY_INPUTS = frozenset(
    {
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
        "requirements-docs.txt",
        "pyproject.hash",
        "lib/pymedphys/dependency-extra.txt",
        "lib/pymedphys/_version.py",
    }
)
# Shared CI configuration defines how the integration and database jobs run.
CI_CONFIGURATION_FILES = frozenset({".github/workflows/ci.yml"})
CI_CONFIGURATION_ROOTS = (".github/actions/",)
# Only integration tests run the CI tooling tests on Windows and macOS and run
# the example scripts.
INTEGRATION_FILES = frozenset({".github/workflows/integration-tests.yml"})
INTEGRATION_ROOTS = (".github/scripts/", "examples/")
# VCS filters affect built archives even when editable imports still work.
PACKAGING_FILTER_NAMES = frozenset({".gitignore", ".gitattributes", ".hgignore"})
# Unit runs skip slow tests and never run doctests, so only integration tests
# validate these modules. Tests require each list to equal what a scan of the
# package finds, so adding, removing or renaming a module must update it here.
SLOW_TEST_FILES = frozenset(
    {
        "lib/pymedphys/tests/delivery/test_deliverydata_trf_dicom_round_trip.py",
        "lib/pymedphys/tests/dicom/test_anonymise.py",
        "lib/pymedphys/tests/experimental/pseudonymisation/test_pseudonymisation.py",
        "lib/pymedphys/tests/gamma/test_agnew_mcgarry.py",
        "lib/pymedphys/tests/metersetmap/test_metersetmap_regression.py",
        "lib/pymedphys/tests/pinnacle/test_pinnacle.py",
        "lib/pymedphys/tests/pinnacle/test_pinnacle_cli.py",
        "lib/pymedphys/tests/trf/test_decode.py",
    }
)
# The scan also covers the directories conftest.py excludes from the doctest
# run, so changing those exclusions cannot leave a module unselected.
DOCTEST_FILES = frozenset(
    {
        "lib/pymedphys/_experimental/cube.py",
        "lib/pymedphys/_gamma/__init__.py",
        "lib/pymedphys/_metersetmap/metersetmap.py",
        "lib/pymedphys/_mosaiq/api.py",
        "lib/pymedphys/_mosaiq/sessions.py",
        "lib/pymedphys/interpolate.py",
    }
)
# Blob modes of ordinary files; 000000 marks the absent side of an addition or
# a deletion. A symlink (120000) or submodule (160000) can stand in for any
# content, so its name says nothing about which checks it affects.
REGULAR_MODES = frozenset({"000000", "100644", "100755"})
RAW_RECORD = re.compile(rb":([0-7]{6}) ([0-7]{6}) [0-9a-f]+ [0-9a-f]+ [A-Z]")
# Policies under which one unrecognised path selects a broad fallback.
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


def _configures_ci(name: str) -> bool:
    return name in CI_CONFIGURATION_FILES or name.startswith(CI_CONFIGURATION_ROOTS)


def _is_shared_test_input(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.name == "conftest.py"
        or name.startswith(SHARED_PREFIXES)
        or (path.parent == PurePosixPath("lib/pymedphys") and path.suffix == ".py")
    )


def _is_integration_input(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        name in DEPENDENCY_INPUTS
        or _configures_ci(name)
        or name in INTEGRATION_FILES
        or name.startswith(INTEGRATION_ROOTS)
        or path.name in PACKAGING_FILTER_NAMES
        or name in SLOW_TEST_FILES
        or name in DOCTEST_FILES
        or _is_shared_test_input(name)
        # A non-Python fixture may be consumed only by a slow test.
        or (name.startswith(TESTS_ROOT) and path.suffix != ".py")
    )


def _is_database_input(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        any("mosaiq" in part or "database" in part for part in path.parts)
        or _is_shared_test_input(name)
        or name in DEPENDENCY_INPUTS
        or _configures_ci(name)
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
        elif kind == "unclassified":
            # Dependencies, non-Python fixtures, build/CI configuration and
            # unknown paths can affect any standard check. A deny-list of
            # extensions would silently miss new consumers and is avoided.
            select(STANDARD, Reason("unclassified input", change.name))
        else:
            # A link can stand in for any content, so nothing is exempt.
            select(PATH_SELECTABLE, Reason("symlink or submodule", change.name))
        # The costly checks run for inputs that no standard check validates.
        if kind in {"python", "unclassified"}:
            if _is_integration_input(change.name):
                select(["run-integration"], Reason("integration input", change.name))
            if _is_database_input(change.name):
                select(["run-database"], Reason("database input", change.name))
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
        # A link selects the most, so name it first.
        first = min(fallback, key=lambda change: change.regular)
        what = (
            "a symlink or submodule, so it selects every check that a changed path "
            "can select"
            if not first.regular
            else "not a recognised documentation or package Python input, so it "
            "selects every standard check"
        )
        count = len(fallback) - 1
        others = (
            f" {count} more changed {'path is' if count == 1 else 'paths are'} "
            "also unclassified."
            if count
            else ""
        )
        lines += ["", f"Fallback: {_code(first.name)} is {what}.{others}"]
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
