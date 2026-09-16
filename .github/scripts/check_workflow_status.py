"""Fail workflow summaries when dependencies fail or required checks are skipped."""

import argparse
import json
import os
from pathlib import Path


def check_jobs(needs, conditional_jobs):
    """Return failures; unlisted dependencies are required to succeed.

    Conditional jobs may be skipped only when their selection output from the
    changes job is explicitly false. Missing outputs fail closed.
    """
    failures = []
    selection = needs.get("changes", {}).get("outputs", {})
    if "changes" not in needs:
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


def make_summary(title, needs, conditional_jobs, failures):
    selection = needs.get("changes", {}).get("outputs", {})
    lines = [f"## {title}", "", "| Check | Required | Status |", "|---|---|---|"]
    for job, details in needs.items():
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--conditional",
        action="append",
        default=[],
        metavar="JOB=OUTPUT",
        help="Allow JOB to be skipped when changes.outputs.OUTPUT is false.",
    )
    args = parser.parse_args()
    conditional_jobs = dict(item.split("=", 1) for item in args.conditional)
    needs = json.loads(os.environ["NEEDS_JSON"])
    failures = check_jobs(needs, conditional_jobs)
    summary = make_summary(args.title, needs, conditional_jobs, failures)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(summary)
    for failure in failures:
        print(f"::error::{failure}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
