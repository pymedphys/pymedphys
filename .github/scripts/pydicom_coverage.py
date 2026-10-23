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

BASELINE_OS = "ubuntu-latest"
BASELINE_PYTHON = "3.14"
BASELINE_ARTIFACT = "junit-ubuntu-latest-3.14"
BASELINE_METADATA = "pydicom-ubuntu-latest-3.14.json"
# Each cell of the unit-test matrix runs in these parts on separate runners,
# and each cell's report is their combination; the Ubuntu/Python 3.14 cell's
# is the baseline.
PARTS = ("corpus-runs", "others")
RESULTS = Path("test-results")


def cell_artifact(os_name: str, python: str) -> str:
    """Name a cell's report as the release's ``junit-*-latest-*`` reads it."""
    if not re.fullmatch(r"[a-z]+-latest", os_name):
        raise ValueError(f"Unknown runner: {os_name!r}")
    if not re.fullmatch(r"3\.[0-9]+", python):
        raise ValueError(f"Unknown Python version: {python!r}")
    return f"junit-{os_name}-{python}"


def part_artifact(
    part: str, os_name: str = BASELINE_OS, python: str = BASELINE_PYTHON
) -> str:
    """Name a part's report so that the release's pattern leaves it out:
    ``-latest`` ends the name, never followed by a hyphen."""
    if part not in PARTS:
        raise ValueError(f"Unknown part: {part!r}")
    cell_artifact(os_name, python)
    return f"junit-py{python}-{part}-{os_name}"


def part_metadata(part: str) -> str:
    return f"{part_artifact(part).replace('junit-', 'pydicom-', 1)}.json"


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


def checked_locked(lock: dict, actual: str) -> str | None:
    actual = version(actual)
    locked = locked_version(lock)
    if locked is not None and actual != locked:
        raise ValueError(
            f"The locked suite imported pydicom {actual}, expected {locked}."
        )
    return locked


def record_part(lock: dict, part: str, actual: str, commit: str, results: Path) -> dict:
    """Bind one part's passing report to the version that part imported."""
    artifact = part_artifact(part)
    commit = commit_sha(commit)
    locked = checked_locked(lock, actual)
    check_junit(results / f"{artifact}.xml")
    metadata = {
        "format": "pymedphys-pydicom-part/1",
        "part": part,
        "commit": commit,
        "actual_version": actual,
        "actual_python_version": platform.python_version(),
        "locked_version": locked,
        "junit": f"{artifact}.xml",
    }
    write_json(results / part_metadata(part), metadata)
    return metadata


def combine_reports(
    results: Path, os_name: str = BASELINE_OS, python: str = BASELINE_PYTHON
) -> Path:
    """Write every part's test cases into the cell's one report.

    Failed and skipped cases are kept, so the combined report shows them. A
    missing part, or a case that two parts both ran, writes no report.
    """
    output = results / f"{cell_artifact(os_name, python)}.xml"
    combined = ET.Element("testsuites")
    seen: dict[tuple[str, str], str] = {}
    for part in PARTS:
        path = results / f"{part_artifact(part, os_name, python)}.xml"
        refuse_dtd(path)
        # nosemgrep: python.lang.security.use-defused-xml-parse
        root = ET.parse(path).getroot()  # nosec B314
        if root.tag == "testsuite":
            suites = [root]
        elif root.tag == "testsuites":
            suites = list(root)
        else:
            raise ValueError(f"{path} is not a JUnit XML report")
        cases = {
            (case.get("classname", ""), case.get("name", ""))
            for case in root.iter("testcase")
        }
        overlap = sorted(cases & seen.keys())
        if overlap:
            raise ValueError(
                f"{'::'.join(overlap[0])} ran in both {seen[overlap[0]]} and {part}."
            )
        seen.update(dict.fromkeys(cases, part))
        combined.extend(suites)
    ET.ElementTree(combined).write(output, encoding="utf-8", xml_declaration=True)
    return output


def part_versions(lock: dict, commit: str, results: Path) -> tuple[str, dict[str, str]]:
    """Return the pydicom version every part imported and each part's Python.

    The parts must agree on pydicom, which must be the locked version. Each
    part's Python need only be 3.14: the parts run on separate runners, whose
    images can carry different 3.14 patch releases while GitHub rolls one out.
    """
    commit = commit_sha(commit)
    found = set()
    pythons = {}
    for part in PARTS:
        path = results / part_metadata(part)
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if (
            metadata.get("format") != "pymedphys-pydicom-part/1"
            or metadata.get("part") != part
            or metadata.get("commit") != commit
            or metadata.get("junit") != f"{part_artifact(part)}.xml"
        ):
            raise ValueError(f"Invalid part evidence in {path}")
        checked_locked(lock, metadata.get("actual_version", ""))
        python = metadata.get("actual_python_version")
        if not isinstance(python, str) or not python.startswith("3.14."):
            raise ValueError(f"The {part} part ran Python {python!r}, expected 3.14.")
        found.add(metadata["actual_version"])
        pythons[part] = python
    if len(found) != 1:
        raise ValueError(
            f"The parts imported different pydicom versions: {sorted(found)}"
        )
    return found.pop(), pythons


def record_baseline(
    lock: dict,
    actual: str,
    commit: str,
    results: Path,
    part_pythons: dict[str, str] | None = None,
) -> dict:
    """Bind the normal Ubuntu/Python 3.14 report to the version actually imported.

    ``part_pythons`` maps each part to the Python it ran, since the combining
    job's own Python is not the one the tests ran under.
    """
    commit = commit_sha(commit)
    locked = checked_locked(lock, actual)
    # Validate the report separately: upload-artifact only requires some files
    # to exist, whereas successful reuse requires both XML and metadata.
    check_junit(results / f"{BASELINE_ARTIFACT}.xml")
    metadata = {
        "format": "pymedphys-pydicom-baseline/1",
        "commit": commit,
        "actual_version": actual,
        "actual_python_version": (
            ", ".join(sorted(set(part_pythons.values())))
            if part_pythons
            else platform.python_version()
        ),
        "locked_version": locked,
        "artifact": BASELINE_ARTIFACT,
        "junit": f"{BASELINE_ARTIFACT}.xml",
        "parts": list(PARTS),
    }
    if part_pythons:
        metadata["part_python_versions"] = part_pythons
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
    elif command == "part":
        import pydicom

        record_part(
            lock,
            os.environ["PART"],
            pydicom.__version__,
            checked_commit(os.environ["CI_COMMIT"]),
            RESULTS,
        )
    elif command == "combine":
        combine_reports(RESULTS, os.environ["CELL_OS"], os.environ["CELL_PYTHON"])
    elif command == "baseline":
        commit = checked_commit(os.environ["CI_COMMIT"])
        actual, part_pythons = part_versions(lock, commit, RESULTS)
        record_baseline(lock, actual, commit, RESULTS, part_pythons)
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
