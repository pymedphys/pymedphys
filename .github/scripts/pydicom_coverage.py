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

"""Record real pydicom test evidence, reusing the locked suite when equivalent."""

import json
import os
import platform
import re
import subprocess
import sys
import tomllib

# The reports come from pytest in this workflow and ElementTree expands no
# external entities; check_junit also refuses any DTD before parsing. The
# reuse path runs under the runner's bare Python, which lacks defusedxml.
import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path
from xml.parsers import expat

BASELINE_ARTIFACT = "junit-ubuntu-latest-3.14"
BASELINE_METADATA = "pydicom-ubuntu-latest-3.14.json"
RESULTS = Path("test-results")


def version(value: str) -> str:
    """Reject malformed resolver output before it reaches an overlay or output."""
    if not re.fullmatch(r"[0-9][0-9A-Za-z.!+_-]*", value):
        raise ValueError(f"Invalid pydicom version: {value!r}")
    return value


def commit_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Coverage needs the tested commit SHA.")
    return value


def checked_commit(expected: str) -> str:
    expected = commit_sha(expected)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise ValueError(
            f"Coverage commit {expected} differs from the checkout {actual}."
        )
    return expected


def minimum_version(project: dict, minimum: str) -> str:
    """Require the job's minimum to match every direct pydicom declaration."""
    declarations = [
        item
        for requirements in (
            project["project"].get("dependencies", []),
            *project["project"]["optional-dependencies"].values(),
            *project.get("dependency-groups", {}).values(),
        )
        for item in requirements
        if isinstance(item, str) and item.lower().startswith("pydicom")
    ]
    expected = f"pydicom>={version(minimum)}"
    if not declarations or any(item != expected for item in declarations):
        raise ValueError(
            f"Pydicom declarations must match {expected!r}: {declarations}"
        )
    return minimum


def locked_version(lock: dict) -> str | None:
    """Only one unambiguous PyPI package can prove equivalent locked coverage."""
    packages = [
        item for item in lock.get("package", []) if item.get("name") == "pydicom"
    ]
    if len(packages) != 1:
        return None
    package = packages[0]
    if package.get("source") != {"registry": "https://pypi.org/simple"}:
        return None
    try:
        return version(package.get("version", ""))
    except (TypeError, ValueError):
        return None


def make_plan(
    lock: dict,
    role: str,
    requested: str,
    quick: bool,
    python_matrix: list[str],
    extra_args: str,
    commit: str,
) -> dict:
    """Map one requested role to its actual run or the complete locked suite."""
    if role not in ("minimum", "latest"):
        raise ValueError(f"Unknown pydicom role: {role!r}")
    if not isinstance(quick, bool):
        raise ValueError("Missing or invalid quick selection.")
    requested = version(requested)
    commit = commit_sha(commit)
    if not isinstance(python_matrix, list) or any(
        not isinstance(item, str) for item in python_matrix
    ):
        raise ValueError("The Python matrix must be a list of version strings.")
    locked = locked_version(lock)
    reuse = (
        (quick or "3.14" in python_matrix) and not extra_args and locked == requested
    )
    artifact = BASELINE_ARTIFACT if reuse else f"junit-pydicom-{role}"
    return {
        "format": "pymedphys-pydicom-coverage/1",
        "role": role,
        "requested_version": requested,
        "locked_version": locked,
        "commit": commit,
        "mode": "reuse" if reuse else "execute",
        "python_version": "3.14",
        "artifact": artifact,
        "junit": f"{artifact}.xml",
        "metadata": BASELINE_METADATA if reuse else f"pydicom-coverage-{role}.json",
        "metadata_artifact": artifact if reuse else f"pydicom-coverage-{role}",
    }


def refuse_dtd(path: Path) -> None:
    """Reject DTDs, the only route to entity expansion; pytest writes none."""

    def refuse(*_):
        raise ValueError(f"Unexpected DTD in {path}")

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    with path.open("rb") as file:
        parser.ParseFile(file)


def check_junit(path: Path) -> None:
    """Require readable, nonempty test evidence with no failed or errored cases."""
    refuse_dtd(path)
    # nosemgrep: python.lang.security.use-defused-xml-parse
    root = ET.parse(path).getroot()  # nosec B314
    if (
        root.tag not in ("testsuite", "testsuites")
        or not list(root.iter("testcase"))
        or any(
            item.tag in ("failure", "error")
            or int(item.get("failures", "0")) != 0
            or int(item.get("errors", "0")) != 0
            for item in root.iter()
        )
    ):
        raise ValueError(f"No successful test evidence in {path}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if json.loads(path.read_text(encoding="utf-8")) != data:
        raise ValueError(f"Invalid coverage metadata in {path}")


def read_toml(filename: str) -> dict:
    return tomllib.loads(Path(filename).read_text(encoding="utf-8"))


def record_baseline(lock: dict, actual: str, commit: str, results: Path) -> dict:
    """Bind the normal Ubuntu/Python 3.14 report to the version actually imported."""
    actual = version(actual)
    commit = commit_sha(commit)
    locked = locked_version(lock)
    if locked is not None and actual != locked:
        raise ValueError(
            f"The locked suite imported pydicom {actual}, expected {locked}."
        )
    # Validate the report separately: upload-artifact only requires some files
    # to exist, whereas successful reuse requires both XML and metadata.
    check_junit(results / f"{BASELINE_ARTIFACT}.xml")
    metadata = {
        "format": "pymedphys-pydicom-baseline/1",
        "commit": commit,
        "actual_version": actual,
        "actual_python_version": platform.python_version(),
        "locked_version": locked,
        "artifact": BASELINE_ARTIFACT,
        "junit": f"{BASELINE_ARTIFACT}.xml",
    }
    write_json(results / BASELINE_METADATA, metadata)
    return metadata


def record_coverage(plan: dict, actual: str | None, results: Path) -> dict:
    """Record a tested overlay or a reference whose success the workflow requires."""
    role = plan["role"]
    version(plan["requested_version"])
    commit_sha(plan["commit"])
    if role not in ("minimum", "latest") or plan["mode"] not in ("execute", "reuse"):
        raise ValueError("Invalid pydicom coverage plan.")
    artifact = BASELINE_ARTIFACT if plan["mode"] == "reuse" else f"junit-pydicom-{role}"
    metadata = (
        BASELINE_METADATA
        if plan["mode"] == "reuse"
        else f"pydicom-coverage-{role}.json"
    )
    metadata_artifact = (
        artifact if plan["mode"] == "reuse" else f"pydicom-coverage-{role}"
    )
    if (
        plan["format"] != "pymedphys-pydicom-coverage/1"
        or plan["python_version"] != "3.14"
        or plan["artifact"] != artifact
        or plan["junit"] != f"{artifact}.xml"
        or plan["metadata"] != metadata
        or plan["metadata_artifact"] != metadata_artifact
    ):
        raise ValueError("Invalid pydicom report reference.")
    plan = {**plan, "coverage_job_python_version": platform.python_version()}
    if plan["mode"] == "execute":
        if actual is None or actual != plan["requested_version"]:
            raise ValueError(
                f"The overlay imported pydicom {actual}, expected {plan['requested_version']}."
            )
        check_junit(results / plan["junit"])
        plan = {
            **plan,
            "actual_version": version(actual),
            "actual_python_version": platform.python_version(),
        }
    elif plan["mode"] != "reuse" or plan["locked_version"] != plan["requested_version"]:
        raise ValueError("Invalid pydicom reuse plan.")
    write_json(results / f"pydicom-coverage-{plan['role']}.json", plan)
    return plan


def main() -> None:
    command = sys.argv[1]
    lock = read_toml("uv.lock")
    if command == "minimum":
        project = read_toml("pyproject.toml")
        print(minimum_version(project, os.environ["PYDICOM_MINIMUM"]))
    elif command == "plan":
        quick = os.environ["QUICK"]
        if quick not in ("true", "false"):
            raise ValueError("Missing or invalid quick selection.")
        plan = make_plan(
            lock,
            os.environ["PYDICOM"],
            os.environ["PYDICOM_VERSION"],
            quick == "true",
            json.loads(os.environ["PYTHON_MATRIX"]),
            os.environ["EXTRA_PYTEST_ARGS"],
            checked_commit(os.environ["CI_COMMIT"]),
        )
        write_json(RESULTS / f"pydicom-plan-{plan['role']}.json", plan)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(
                f"version={plan['requested_version']}\nreuse={str(plan['mode'] == 'reuse').lower()}\n"
            )
    elif command == "baseline":
        import pydicom

        record_baseline(
            lock, pydicom.__version__, checked_commit(os.environ["CI_COMMIT"]), RESULTS
        )
    elif command == "record":
        plan = json.loads(
            (RESULTS / f"pydicom-plan-{os.environ['PYDICOM']}.json").read_text(
                encoding="utf-8"
            )
        )
        actual = None
        if plan["mode"] == "execute":
            import pydicom

            actual = pydicom.__version__
        plan = record_coverage(plan, actual, RESULTS)
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open(
            "a", encoding="utf-8"
        ) as summary:
            summary.write(
                "## Pydicom coverage\n\n| Role | Version | Evidence | Report artifact |\n"
                "|---|---|---|---|\n"
                f"| {plan['role']} | {plan['requested_version']} | {plan['mode']} | {plan['artifact']} |\n\n"
                f"Commit: `{plan['commit']}`. Reused evidence requires the normal Ubuntu/Python 3.14 job to pass.\n"
            )
    else:
        raise ValueError(f"Unknown command: {command!r}")


if __name__ == "__main__":
    main()
