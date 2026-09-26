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
import subprocess
from pathlib import Path, PurePosixPath

OUTPUTS = (
    "run-python",
    "run-docs",
    "run-integration",
    "run-database",
    "run-scripts",
    "run-dependency-audit",
    "run-python-security",
    "run-workflow-audit",
)
DOC_ROOTS = ("docs/", "lib/pymedphys/docs/")
# Only prose and rendered assets are exempt from Python checks. A Python file,
# configuration file or new file type in the docs directory remains executable
# input until its consumers have been reviewed.
DOC_SUFFIXES = {
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
ROOT_DOCS = {
    "README.rst",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    "AGENTS.md",
    "SECURITY.md",
}


def select_checks(paths, *, event_name="pull_request", labels=()):
    """Return explicit booleans for every gate, never an incomplete selection."""
    if paths is None or event_name != "pull_request" or "full-test" in labels:
        selected = dict.fromkeys(OUTPUTS, True)
        # ReadTheDocs publishes main independently; retain the existing policy.
        if event_name == "push":
            selected["run-docs"] = False
        return selected

    selected = dict.fromkeys(OUTPUTS, False)
    selected["run-database"] = "database" in labels
    for name in paths:
        path = PurePosixPath(name)
        if name in ROOT_DOCS or (
            name.startswith(DOC_ROOTS) and path.suffix in DOC_SUFFIXES
        ):
            selected["run-docs"] = True
        elif name.startswith("lib/pymedphys/") and path.suffix == ".py":
            selected["run-python"] = True
            selected["run-python-security"] = True
            # Online audits have changing external inputs even when the lockfile
            # and workflows are untouched. Retain their existing PR cadence.
            selected["run-dependency-audit"] = True
            selected["run-workflow-audit"] = True
            if not name.startswith("lib/pymedphys/tests/"):
                selected["run-docs"] = True
            if any("mosaiq" in part or "database" in part for part in path.parts):
                selected["run-database"] = True
            # Shared imports, fixtures and data access can affect database tests.
            if (
                path.name == "conftest.py"
                or name.startswith(
                    (
                        "lib/pymedphys/_imports/",
                        "lib/pymedphys/_data/",
                        "lib/pymedphys/_utilities/",
                        "lib/pymedphys/_base/",
                    )
                )
                or path.parent == PurePosixPath("lib/pymedphys")
            ):
                selected["run-database"] = True
        else:
            # Dependencies, non-Python fixtures, build/CI configuration and
            # unknown paths can affect any check. A deny-list of extensions
            # would silently miss new consumers and is deliberately avoided.
            return dict.fromkeys(OUTPUTS, True)
    return selected


def changed_paths(event, *, git=subprocess.check_output):
    """Return all changed paths, or None if the tested merge is unprovable."""
    try:
        pr = event["pull_request"]
        expected = [pr["base"]["sha"], pr["head"]["sha"]]
        parents = git(["git", "show", "-s", "--format=%P", "HEAD"]).decode().split()
        if parents != expected:
            return None
        diff = git(
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                "HEAD^1",
                "HEAD",
                "--",
            ]
        )
        # NUL delimiters preserve spaces, newlines and shell metacharacters.
        return [part.decode("utf-8") for part in diff.split(b"\0") if part]
    except (KeyError, TypeError, UnicodeError, OSError, subprocess.CalledProcessError):
        return None


def main():
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    paths = changed_paths(event) if event_name == "pull_request" else None
    labels = [
        label["name"] for label in event.get("pull_request", {}).get("labels", [])
    ]
    selected = select_checks(paths, event_name=event_name, labels=labels)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for name, enabled in selected.items():
            output.write(f"{name}={str(enabled).lower()}\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write("## Check selection\n\n| Check | Selected |\n| --- | --- |\n")
        for name, enabled in selected.items():
            summary.write(f"| {name} | {'yes' if enabled else 'no'} |\n")
        if paths is None and event_name == "pull_request":
            summary.write(
                "\nThe merge diff could not be verified; all checks are selected.\n"
            )


if __name__ == "__main__":
    main()
