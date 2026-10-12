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

"""Explicit commands: planning and reporting never invoke implementations."""

from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sys

from .common import SCHEMA_VERSION, read_json, write_json
from .runner import (
    DEFAULT_SETTINGS,
    example_config,
    execute_run,
    resolved_config,
    validate_plan,
)
from .workloads import case_id, make_plan


def describe(plan):
    counts = Counter((case["dimension"], case["study"]) for case in plan["cases"])
    print(f"{len(plan['cases'])} cases; {plan['repeats']} matched rounds per case.")
    for (dimension, study), count in sorted(counts.items()):
        print(f"  {dimension}D {study}: {count}")
    print("Planning only. No gamma implementation has been imported or executed.")


def generate_plan(args):
    plan = make_plan(args.preset)
    if getattr(args, "repeats", None) is not None:
        plan["repeats"] = args.repeats
    if getattr(args, "study", None):
        requested = set(args.study)
        available = {case["study"] for case in plan["cases"]}
        if requested - available:
            raise ValueError(
                f"Unknown studies: {', '.join(sorted(requested - available))}"
            )
        plan["cases"] = [case for case in plan["cases"] if case["study"] in requested]
    if getattr(args, "dimension", None):
        plan["cases"] = [
            case for case in plan["cases"] if case["dimension"] == args.dimension
        ]
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare PyMedPhys gamma versions, branches or interpolators. Only the run command executes gamma."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Create editable configuration and a frozen plan; no execution"
    )
    init.add_argument("--directory", type=Path, required=True)
    init.add_argument(
        "--preset", choices=["quick", "standard", "thorough"], default="standard"
    )
    init.add_argument(
        "--baseline-checkout",
        type=Path,
        help="Existing PyMedPhys checkout for the baseline",
    )
    init.add_argument(
        "--candidate-checkout",
        type=Path,
        help="Existing PyMedPhys checkout for the candidate",
    )
    init.add_argument(
        "--compare-interpolators",
        action="store_true",
        help="Compare SciPy and PyMedPhys interpolators in the same baseline checkout",
    )
    plan_parser = commands.add_parser(
        "plan", help="Write a plan without importing an implementation"
    )
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument(
        "--preset", choices=["quick", "standard", "thorough"], default="standard"
    )
    plan_parser.add_argument("--repeats", type=int)
    plan_parser.add_argument(
        "--study", action="append", help="Select a study; repeat to select several"
    )
    plan_parser.add_argument("--dimension", type=int, choices=[2, 3])
    matrix = commands.add_parser(
        "matrix", help="Expand a JSON template + factors into a custom factorial plan"
    )
    matrix.add_argument("--design", type=Path, required=True)
    matrix.add_argument("--output", type=Path, required=True)
    check = commands.add_parser(
        "check",
        help="Validate configuration and plan without importing implementations",
    )
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--plan", type=Path, required=True)
    check.add_argument(
        "--allow-missing-checkouts",
        action="store_true",
        help="Permit placeholder checkout paths during planning",
    )
    run = commands.add_parser(
        "run", help="Benchmark the configured PyMedPhys versions (explicit opt-in)"
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--no-report", action="store_true")
    report = commands.add_parser(
        "report", help="Render saved evidence; never executes gamma"
    )
    report.add_argument(
        "--output", type=Path, required=True, help="Existing run directory"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if args.compare_interpolators and args.candidate_checkout is not None:
                raise ValueError(
                    "--compare-interpolators uses one --baseline-checkout; omit --candidate-checkout"
                )
            directory = args.directory
            if directory.exists() and any(directory.iterdir()):
                raise ValueError("Initialisation requires an empty directory")
            directory.mkdir(parents=True, exist_ok=True)
            plan = generate_plan(args)
            config = example_config(
                args.preset, compare_interpolators=args.compare_interpolators
            )
            checkouts = [
                args.baseline_checkout,
                args.baseline_checkout
                if args.compare_interpolators
                else args.candidate_checkout,
            ]
            for spec, checkout in zip(config["versions"], checkouts):
                if checkout is not None:
                    spec["checkout"] = str(checkout.resolve())
            write_json(directory / "config.json", config)
            write_json(directory / "plan.json", plan)
            describe(plan)
            print(f"Edit {directory / 'config.json'} to select the PyMedPhys versions.")
        elif args.command in {"plan", "matrix"}:
            if args.output.exists():
                raise ValueError(
                    "Refusing to overwrite an existing plan; choose a new output path"
                )
            if args.command == "plan":
                plan = generate_plan(args)
            else:
                design = read_json(args.design)
                template = design["template"]
                factors = design["factors"]
                if not factors or not all(
                    isinstance(v, list) and v for v in factors.values()
                ):
                    raise ValueError("factors must contain non-empty lists")
                cases = []
                for values in itertools.product(*factors.values()):
                    case = dict(template, **dict(zip(factors, values)))
                    case["id"] = case_id(case)
                    cases.append(case)
                plan = dict(
                    schema_version=SCHEMA_VERSION,
                    preset="custom",
                    repeats=design.get("repeats", 5),
                    cases=cases,
                    notes=[
                        "Custom factorial design; factors can interact and must be analysed together."
                    ],
                )
            validate_plan(plan, DEFAULT_SETTINGS)
            write_json(args.output, plan)
            describe(plan)
        elif args.command == "check":
            config = resolved_config(
                args.config, require_checkouts=not args.allow_missing_checkouts
            )
            plan = read_json(args.plan)
            validate_plan(plan, config["settings"])
            describe(plan)
            calls = (
                len(plan["cases"])
                * plan["repeats"]
                * len(config["versions"])
                * (1 + config["settings"]["warmups"])
            )
            print(
                f"If run: {calls} full gamma calls including warm-ups; duration is unknown until measured."
            )
        elif args.command == "run":
            config = resolved_config(args.config)
            summary = execute_run(
                config,
                read_json(args.plan),
                args.output,
                resume=args.resume,
                make_report=not args.no_report,
            )
            print(
                f"Run status: {summary['run_status']}; {summary['validated_cases']}/{summary['planned_cases']} cases validated"
            )
            return 0 if summary["run_status"] == "completed" else 2
        elif args.command == "report":
            if not args.output.is_dir():
                raise ValueError("Report directory does not exist")
            from .report import build_report

            files = build_report(args.output)
            print(f"Rendered {len(files)} files from saved evidence. No gamma calls.")
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
