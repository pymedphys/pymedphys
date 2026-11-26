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

"""Fail workflow summaries when dependencies fail or required checks are skipped."""

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

Needs = Mapping[str, Mapping[str, Any]]


def _selection(needs: Needs) -> Mapping[str, Any]:
    return needs.get("changes", {}).get("outputs", {})


def check_jobs(
    needs: Needs,
    conditional_jobs: Mapping[str, str],
    *,
    merge_group: bool = False,
) -> list[str]:
    """Return failures; unlisted dependencies are required to succeed.

    Conditional jobs may be skipped only when their selection output from the
    changes job is explicitly false. Missing outputs fail closed. A summary
    without conditional jobs, such as the release workflow's, needs no changes
    job. A merge group skips the changes job and runs every conditional job,
    so there the changes job must have been skipped and every other job must
    succeed.
    """
    if not needs:
        return ["The summary has no dependency results to validate."]

    failures: list[str] = []
    if merge_group:
        for job, details in needs.items():
            result = details.get("result")
            expected = "skipped" if job == "changes" else "success"
            if result != expected:
                failures.append(
                    f"{job}: expected {expected} in a merge group, "
                    f"got {result or 'missing'}."
                )
        for job in conditional_jobs:
            if job not in needs:
                failures.append(f"{job}: missing from the summary dependencies.")
        if conditional_jobs and "changes" not in needs:
            failures.append("The changes job is missing from the summary dependencies.")
        return failures
    selection = _selection(needs)
    if conditional_jobs and "changes" not in needs:
        failures.append("The changes job is missing from the summary dependencies.")

    for job, output in conditional_jobs.items():
        if job not in needs:
            failures.append(f"{job}: missing from the summary dependencies.")
        if selection.get(output) not in ("true", "false"):
            failures.append(f"{job}: missing or invalid changes output {output}.")

    for job, details in needs.items():
        result = details.get("result")
        optional = (
            job in conditional_jobs and selection.get(conditional_jobs[job]) == "false"
        )
        accepted = ("success", "skipped") if optional else ("success",)
        if result not in accepted:
            expected = "success or an intentional skip" if optional else "success"
            failures.append(f"{job}: expected {expected}, got {result or 'missing'}.")

    return failures


def make_summary(
    title: str,
    needs: Needs,
    conditional_jobs: Mapping[str, str],
    failures: list[str],
    *,
    merge_group: bool = False,
) -> str:
    selection = _selection(needs)
    lines = [f"## {title}", "", "| Check | Required | Status |", "|---|---|---|"]
    for job, details in needs.items():
        if merge_group:
            required = job != "changes"
        else:
            required = (
                job not in conditional_jobs
                or selection.get(conditional_jobs[job]) != "false"
            )
        lines.append(
            f"| {job} | {'yes' if required else 'no'} | "
            f"{details.get('result', 'missing')} |"
        )

    if needs.get("pre-commit", {}).get("outputs", {}).get("autofix-pushed") == "true":
        lines.extend(
            [
                "",
                "Pre-commit pushed an auto-fix commit. This run does not validate "
                "that commit; its new CI run must pass before merging.",
            ]
        )

    lines.append("")
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("All required checks passed.")
    return "\n".join(lines) + "\n"


def parse_conditional(items: list[str]) -> dict[str, str]:
    """Parse ``JOB=OUTPUT`` arguments, rejecting malformed ones clearly."""
    conditional: dict[str, str] = {}
    for item in items:
        job, _, output = item.partition("=")
        if not job or not output:
            raise SystemExit(f"--conditional expects JOB=OUTPUT, got {item!r}")
        conditional[job] = output
    return conditional


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--conditional",
        action="append",
        default=[],
        metavar="JOB=OUTPUT",
        help="Allow JOB to be skipped when changes.outputs.OUTPUT is false.",
    )
    parser.add_argument(
        "--merge-group-runs-every-check",
        action="store_true",
        help=(
            "In a merge group (GITHUB_EVENT_NAME merge_group), require the "
            "changes job to be skipped and every other job to succeed."
        ),
    )
    args = parser.parse_args()
    conditional_jobs = parse_conditional(args.conditional)
    needs: dict[str, dict[str, Any]] = json.loads(os.environ["NEEDS_JSON"])
    # Without the option a merge group is judged by the changes job's
    # selection, as before; with it, outside a merge group, nothing changes.
    merge_group = (
        args.merge_group_runs_every_check
        and os.environ.get("GITHUB_EVENT_NAME") == "merge_group"
    )
    failures = check_jobs(needs, conditional_jobs, merge_group=merge_group)
    summary = make_summary(
        args.title, needs, conditional_jobs, failures, merge_group=merge_group
    )
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(summary)
    for failure in failures:
        print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
