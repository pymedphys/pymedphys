# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Run a gamma scaling study in the background and package its evidence.

python examples/gamma_scaling_background.py --output gamma-scaling-local
python examples/gamma_scaling_background.py --status gamma-scaling-local
python examples/gamma_scaling_background.py --stop gamma-scaling-local
python examples/gamma_scaling_background.py --resume gamma-scaling-local

The entire run has a two-hour deadline, including warm-ups and reporting.
Stopping interrupts the active worker and preserves completed comparisons.
The upload ZIP excludes the large temporary gamma arrays.
"""

import argparse
import datetime
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

from gamma_scaling_process import start_process, terminate_process

PREVIOUS = "866f83edad8586a42a739094e488f45242b72c95"
SOURCE_FILES = (
    "gamma_scaling_background.py",
    "gamma_scaling.py",
    "gamma_scaling_worker.py",
    "gamma_scaling_process.py",
    "gamma_performance_audit.py",
    "gamma_performance.py",
    "gamma-scaling-requirements.txt",
)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def environment_description():
    packages = sorted(
        {
            distribution.metadata["Name"]: distribution.version
            for distribution in importlib.metadata.distributions()
            if distribution.metadata["Name"]
        }.items()
    )
    return {"python": sys.version, "packages": dict(packages)}


class RunLock:
    """An OS lock prevents simultaneous runs and is released after a crash."""

    def __init__(self, output):
        self.path = output / "run.lock"
        self.stream = None

    def __enter__(self):
        self.stream = self.path.open("a+b")
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise
        return self

    def __exit__(self, *_):
        self.stream.close()


def busy(output):
    try:
        with RunLock(output):
            return False
    except OSError:
        return True


def bundle(output):
    """Whitelist small evidence files; never package working gamma arrays."""
    paths = [
        output / name
        for name in ("run.json", "run-config.json", "run.log", "environment.json")
    ]
    paths += [output / "benchmark-source" / name for name in SOURCE_FILES]
    study = output / "study"
    paths += [
        study / name for name in ("results.json", "audit-plan.json", "calibration.json")
    ]
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))
    if status.get("report_complete", True):
        paths += [
            study / name
            for name in (
                "timings.csv",
                "summary.csv",
                "speed-ratios.csv",
                "speed-ratios.png",
                "speed-ratios.svg",
                "audit-scenarios.png",
                "README.md",
            )
        ]
        paths += list(study.glob("scaling-*.png")) + list(study.glob("scaling-*.svg"))
    target = output / "gamma-scaling-upload.zip"
    temporary = target.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, path.relative_to(output).as_posix())
    temporary.replace(target)
    return target


def remaining_budget(config):
    """Resume never resets the original wall-clock deadline."""
    return max(0.0, config["deadline_unix"] - time.time())


def bundle_with_deadline(output, deadline):
    """Keep even compression inside the total budget."""
    remaining = deadline - time.monotonic()
    if remaining <= 6:
        print(
            "No packaging time remains; raw evidence is in the study directory.",
            flush=True,
        )
        return False
    process = start_process(
        [sys.executable, str(Path(__file__).resolve()), "--bundle", str(output)],
        stdin=subprocess.DEVNULL,
    )
    try:
        # Reserve the bounded process-tree termination time too.
        process.wait(timeout=max(0.01, remaining - 6))
    except subprocess.TimeoutExpired:
        terminate_process(process)
        print("Packaging reached the deadline; raw evidence is preserved.", flush=True)
        return False
    return process.returncode == 0


def supervise(output):
    try:
        lock = RunLock(output)
        lock.__enter__()
    except OSError:
        print("This study already has an active supervisor.", flush=True)
        return 1
    deadline = time.monotonic()
    try:
        config = json.loads((output / "run-config.json").read_text(encoding="utf-8"))
        deadline += remaining_budget(config)
        reserve = min(120.0, config["max_seconds"] * 0.2)
        status = {
            "state": "running",
            "pid": os.getpid(),
            "started_utc": now(),
            "deadline_utc": datetime.datetime.fromtimestamp(
                config["deadline_unix"], datetime.timezone.utc
            ).isoformat(),
            "max_seconds": config["max_seconds"],
        }
        write_json(output / "run.json", status)
        environment = environment_description()
        environment_path = output / "environment.json"
        if environment_path.exists():
            recorded = json.loads(environment_path.read_text(encoding="utf-8"))
            if environment != recorded:
                raise ValueError(
                    "Restore the original Python and package versions before resuming"
                )
        else:
            write_json(environment_path, environment)
        study = output / "study"
        command = [
            sys.executable,
            "-u",
            str(
                output
                / "benchmark-source"
                / (
                    "gamma_scaling.py"
                    if config["quick"]
                    else "gamma_performance_audit.py"
                )
            ),
            "--repo",
            config["repo"],
            "--previous-ref",
            config["previous"],
            "--current-ref",
            config["current"],
            "--threads",
            str(config["threads"]),
            "--worker-timeout",
            str(config["worker_timeout"]),
            "--stop-file",
            str(output / "stop.request"),
            "--deadline",
            str(config["deadline_unix"] - reserve),
        ]
        if config["quick"]:
            command += [
                "--schedule",
                "size-first",
                "--scales",
                "0.02",
                "--round-indices",
                "0",
            ]
        command += [
            "--resume" if (study / "results.json").exists() else "--output",
            str(study),
        ]
        print(
            f"Study started at {now()}; deadline {status['deadline_utc']}. "
            f"Measurements stop {reserve:g} seconds earlier for reporting and packaging.",
            flush=True,
        )
        try:
            process = start_process(
                command, cwd=config["repo"], stdin=subprocess.DEVNULL
            )
            status["driver_pid"] = process.pid
            write_json(output / "run.json", status)
            watchdog = False
            try:
                process.wait(
                    timeout=max(0.01, deadline - reserve / 2 - time.monotonic())
                )
            except subprocess.TimeoutExpired:
                watchdog = True
                terminate_process(process)
                print(
                    "Overall watchdog stopped the driver and workers; preserving the checkpoint.",
                    flush=True,
                )
            exit_code = process.returncode
            result_path = study / "results.json"
            result = (
                json.loads(result_path.read_text(encoding="utf-8"))
                if result_path.exists()
                else {}
            )
            if watchdog or result.get("stop_reason") == "time_budget":
                state = "budget_exhausted"
            elif (output / "stop.request").exists() and not result.get("complete"):
                state = "stopped"
            else:
                state = (
                    "completed"
                    if exit_code == 0 and result.get("complete")
                    else "failed"
                )
            status.update(
                state=state,
                exit_code=exit_code,
                finished_utc=now(),
                complete=bool(result.get("complete")),
                quick=config["quick"],
                report_complete=exit_code == 0 and not watchdog,
                watchdog=watchdog,
            )
        except Exception:  # noqa: BLE001 - Preserve evidence from any failed stage.
            traceback.print_exc()
            status.update(state="failed", finished_utc=now(), report_complete=False)
        write_json(output / "run.json", status)
        print(
            f"Study {status['state']}; preparing gamma-scaling-upload.zip", flush=True
        )
        sys.stdout.flush()
        sys.stderr.flush()
        if bundle_with_deadline(output, deadline):
            print("Upload bundle is ready.", flush=True)
        return 0 if status["state"] in ("completed", "budget_exhausted") else 1
    except Exception:  # noqa: BLE001 - Record setup failures as well as worker failures.
        traceback.print_exc()
        write_json(
            output / "run.json",
            {"state": "failed", "finished_utc": now(), "report_complete": False},
        )
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            bundle_with_deadline(output, deadline)
        except Exception:  # noqa: BLE001 - A packaging error must retain the raw log.
            traceback.print_exc()
        return 1
    finally:
        lock.__exit__()


def show_status(output):
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))
    print(f"State: {status['state']}; supervisor active: {busy(output)}")
    config = json.loads((output / "run-config.json").read_text(encoding="utf-8"))
    if "deadline_unix" in config:
        print(
            f"Remaining wall-clock allowance: {remaining_budget(config) / 60:.1f} minutes"
        )
    result_path = output / "study/results.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        config = result["config"]
        if "plan" in config:
            expected = len(config["plan"]) or 74
        else:
            expected = 1
            for key in ("dimensions", "profiles", "scales", "round_indices"):
                expected *= len(config[key])
        calls = sum(len(r.get("times", [])) for r in result["records"])
        print(
            f"Verified four-way groups: {len(result['comparisons'])}/{expected}; recorded timed calls: {calls}"
        )
    print(f"Progress log: {output / 'run.log'}")
    archive = output / "gamma-scaling-upload.zip"
    if archive.exists() and not busy(output):
        print(f"Upload: {archive}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--output", type=Path)
    action.add_argument("--status", type=Path)
    action.add_argument("--stop", type=Path)
    action.add_argument("--resume", type=Path)
    action.add_argument("--supervise", type=Path, help=argparse.SUPPRESS)
    action.add_argument("--bundle", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--previous-ref", default=PREVIOUS)
    parser.add_argument("--current-ref", default="HEAD")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--worker-timeout", type=int, default=14400)
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=7200,
        help="Total wall-clock budget, including reporting (5–7200; default 7200)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small installation check; not the full study",
    )
    args = parser.parse_args()
    launched = time.time()
    if args.bundle:
        bundle(args.bundle.resolve(strict=True))
        return 0
    if args.supervise:
        return supervise(args.supervise.resolve(strict=True))
    if args.status:
        show_status(args.status.resolve(strict=True))
        return 0
    if args.stop:
        output = args.stop.resolve(strict=True)
        if not busy(output):
            parser.error("This study has no active supervisor")
        (output / "stop.request").touch()
        print(
            "Stop requested. The active worker will be interrupted; completed comparisons are preserved."
        )
        return 0
    if args.resume:
        output = args.resume.resolve(strict=True)
        if busy(output):
            parser.error("This study is already running")
        status = json.loads((output / "run.json").read_text(encoding="utf-8"))
        if status["state"] == "completed":
            parser.error("This study is already complete; its upload ZIP is ready")
        config = json.loads((output / "run-config.json").read_text(encoding="utf-8"))
        if "deadline_unix" not in config:
            parser.error(
                "This older run has no overall deadline. Start a new output directory with the current launcher."
            )
        if remaining_budget(config) <= min(120, config["max_seconds"] * 0.2):
            parser.error(
                "The original study budget is exhausted; resume cannot extend it"
            )
        if Path(config["python"]).resolve() != Path(sys.executable).resolve():
            parser.error("Resume with the original Python environment")
        environment_path = output / "environment.json"
        if environment_path.exists():
            recorded = json.loads(environment_path.read_text(encoding="utf-8"))
            if environment_description() != recorded:
                parser.error(
                    "Restore the original Python and package versions before resuming"
                )
        (output / "stop.request").unlink(missing_ok=True)
        (output / "gamma-scaling-upload.zip").unlink(missing_ok=True)
    else:
        if not 5 <= args.max_seconds <= 7200:
            parser.error("The total budget must be between 5 and 7200 seconds")
        if min(args.threads, args.worker_timeout) < 1:
            parser.error("Use positive thread and timeout settings")
        repo = args.repo.resolve(strict=True)

        def revision(ref):
            return subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                text=True,
            ).strip()

        previous, current = revision(args.previous_ref), revision(args.current_ref)
        if previous == current:
            parser.error("Choose two distinct source revisions")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        output = (args.output or Path(f"gamma-scaling-{timestamp}")).resolve()
        output.mkdir(parents=True, exist_ok=False)
        source = output / "benchmark-source"
        source.mkdir()
        for name in SOURCE_FILES:
            shutil.copy2(Path(__file__).with_name(name), source / name)
        config = {
            "repo": str(repo),
            "python": sys.executable,
            "previous": previous,
            "current": current,
            "threads": args.threads,
            "worker_timeout": args.worker_timeout,
            "quick": args.quick,
            "max_seconds": args.max_seconds,
            "deadline_unix": launched + args.max_seconds,
        }
        write_json(output / "run-config.json", config)
    write_json(output / "run.json", {"state": "starting", "requested_utc": now()})
    command = [
        sys.executable,
        "-u",
        str(output / "benchmark-source/gamma_scaling_background.py"),
        "--supervise",
        str(output),
    ]
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with (output / "run.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=config["repo"],
            close_fds=True,
            **options,
        )
    print(
        f"Started background study (supervisor PID {process.pid}). You can close this terminal."
    )
    print(
        f"Output: {output}\nKeep the workstation awake and avoid other heavy computation."
    )
    print(
        f"Total wall-clock limit: {config['max_seconds'] / 60:g} minutes, including warm-ups and reporting."
    )
    print(
        f'Check progress: python examples/gamma_scaling_background.py --status "{output}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
