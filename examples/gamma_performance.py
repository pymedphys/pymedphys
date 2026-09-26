# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Compare warmed gamma performance between two committed PyMedPhys revisions.

From the repository root, using the project's Python environment:
    python examples/gamma_performance.py

The default comparison uses previous main 866f83e and current HEAD. It creates
temporary detached worktrees, verifies imported source and full-array equality,
then writes a labelled PNG/SVG, raw timings and provenance to a new directory.
No patient data or downloads are required. Git and an environment with the
PyMedPhys gamma dependencies, NumPy and Matplotlib must already be available.
The notebook at docs/contrib/info/gamma-performance explains the methodology.
"""

import numpy as np

# Optional: provide two checkouts and their exact 40-character commit IDs.
# Leaving both paths unset skips the benchmark; invalid configured paths fail.
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CASES = ["3d", "3d-maxgamma", "3d-local", "3d-scipy", "2d", "2d-scipy"]


def checked_checkout(path, revision):
    root = Path(path).resolve(strict=True)
    if not (root / "lib" / "pymedphys" / "__init__.py").is_file():
        raise ValueError(f"No PyMedPhys source tree at {root}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ValueError("Specify the exact 40-character commit ID, not a branch name")

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()

    if git("rev-parse", "HEAD") != revision:
        raise ValueError(f"{root} is not at the requested revision {revision}")
    # Notebook outputs may be dirty; imported source and dependencies may not.
    changes = git(
        "status",
        "--porcelain",
        "--",
        ":(glob)lib/pymedphys/**/*.py",
        "pyproject.toml",
        "uv.lock",
    )
    if changes:
        raise ValueError(f"Benchmark source/dependency files are modified: {changes}")
    return root


def run_benchmark(
    previous_path,
    previous_revision,
    current_path,
    current_revision,
    cases=CASES,
    rounds=3,
    repeats=2,
    threads=2,
    progress_path=None,
):
    roots = {
        "previous": checked_checkout(previous_path, previous_revision),
        "current": checked_checkout(current_path, current_revision),
    }
    if roots["previous"] == roots["current"] or previous_revision == current_revision:
        raise ValueError("The benchmark requires two distinct checkouts and revisions")
    if not cases or any(case not in CASES for case in cases):
        raise ValueError("Select at least one supported benchmark case")
    if min(rounds, repeats, threads) < 1:
        raise ValueError("Rounds, repeats and threads must be positive")
    records, arrays, timings = (
        [],
        {},
        {case: {version: [] for version in roots} for case in cases},
    )
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        worker_path = directory / "worker.py"
        worker_path.write_text(WORKER, encoding="utf-8")
        for round_index in range(rounds):
            for case in cases:
                order = (
                    ["previous", "current"]
                    if round_index % 2 == 0
                    else ["current", "previous"]
                )
                for version in order:
                    array_path = directory / f"{case}-{version}-{round_index}.npy"
                    root = roots[version]
                    print(
                        f"Round {round_index + 1}/{rounds}: {case}, {version}",
                        flush=True,
                    )
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(worker_path),
                            case,
                            str(repeats),
                            str(root),
                            str(array_path),
                        ],
                        env=dict(
                            os.environ,
                            PYTHONPATH=str(root / "lib"),
                            NUMBA_NUM_THREADS=str(threads),
                            PYTHONDONTWRITEBYTECODE="1",
                        ),
                        cwd=directory,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=600,
                    )
                    record = json.loads(result.stdout)
                    print(f"  {record['times']} s", flush=True)
                    for origin in record["origins"].values():
                        if (
                            not Path(origin)
                            .resolve()
                            .is_relative_to(root / "lib" / "pymedphys")
                        ):
                            raise RuntimeError(
                                f"Unexpected import provenance: {origin}"
                            )
                    gamma_values = np.load(array_path, allow_pickle=False)
                    if case in arrays:
                        # Compare every element and NaN position, across versions and rounds.
                        np.testing.assert_array_equal(gamma_values, arrays[case])
                    else:
                        arrays[case] = gamma_values
                    record.update(
                        version=version,
                        round=round_index,
                        revision=previous_revision
                        if version == "previous"
                        else current_revision,
                    )
                    record["origins"] = {
                        name: Path(origin).relative_to(root).as_posix()
                        for name, origin in record["origins"].items()
                    }
                    record["gamma_sha256"] = hashlib.sha256(
                        gamma_values.tobytes()
                    ).hexdigest()
                    record["elementwise_equal"] = True
                    records.append(record)
                    if progress_path is not None:
                        Path(progress_path).write_text(
                            json.dumps(records, indent=2), encoding="utf-8"
                        )
                    timings[case][version].extend(record["times"])
    for version, root in roots.items():
        checked_checkout(
            root, previous_revision if version == "previous" else current_revision
        )
    return {
        "times": timings,
        "records": records,
        "elementwise_equal": True,
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
        "rounds": rounds,
        "repeats": repeats,
        "threads": threads,
    }


WORKER = r'''
"""Time pymedphys.gamma on fixed synthetic cases; run once per source tree.

Usage: python bench_worker.py CASE REPEATS CHECKOUT OUTPUT_NPY
Checks module origins, saves the full gamma array and prints timing/provenance JSON.
"""

import json
import hashlib
import importlib
import platform
from pathlib import Path
import numba
import scipy
import sys
import time
import warnings

import numpy as np
import scipy.ndimage

import pymedphys


def field(axes, centre_shift=(0.0, 0.0, 0.0), scale=1.0):
    """Smooth synthetic dose: two crossing fields and a boost."""
    grids = np.meshgrid(*axes, indexing="ij")
    ndim = len(axes)
    dose = np.zeros(grids[0].shape)

    def box(half_widths, centre, weight):
        inside = np.ones(grids[0].shape, dtype=bool)
        for g, h, c, s in zip(grids, half_widths, centre, centre_shift):
            inside &= np.abs(g - c - s) <= h
        return weight * inside

    centre = [0.0] * ndim
    dose += box([40, 60, 25][:ndim], centre, 1.0)
    dose += box([55, 30, 45][:ndim], centre, 0.8)
    dose += box([15, 15, 15][:ndim], [5, -8, 4][:ndim], 0.6)
    spacing = [a[1] - a[0] for a in axes]
    sigma = [6.0 / s for s in spacing]
    dose = scipy.ndimage.gaussian_filter(dose, sigma, mode="constant")
    return 2.0 * scale * dose / dose.max()


def case_inputs(case):
    if case.startswith("3d"):
        ref_axes = tuple(np.arange(-n, n + 1e-9, 2.5) for n in (50.0, 70.0, 70.0))
        eval_axes = ref_axes
    elif case.startswith("2d"):
        ref_axes = tuple(np.arange(-n, n + 1e-9, 0.5) for n in (100.0, 100.0))
        eval_axes = ref_axes
    else:
        raise ValueError(case)
    ndim = len(ref_axes)
    ref = field(ref_axes)
    ev = field(eval_axes, centre_shift=(1.0, -0.7, 0.5)[:ndim], scale=1.02)
    options = dict(
        dose_percent_threshold=3,
        distance_mm_threshold=3,
        lower_percent_dose_cutoff=10,
    )
    if "scipy" in case:
        options["interp_algo"] = "scipy"
    if "local" in case:
        options.update(dose_percent_threshold=2, distance_mm_threshold=2, local_gamma=True)
    if "maxgamma" in case:
        options["max_gamma"] = 2
    return ref_axes, ref, eval_axes, ev, options


def main():
    case, repeats = sys.argv[1], int(sys.argv[2])
    ref_axes, ref, eval_axes, ev, options = case_inputs(case)
    root = Path(sys.argv[3]).resolve()
    origins = {}
    for name in ("pymedphys", "pymedphys._gamma.implementation.shell", "pymedphys._interp.interp"):
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(root / "lib" / "pymedphys"):
            raise RuntimeError(f"Wrong imported module: {name} from {origin}; expected {root}")
        origins[name] = str(origin)
    warnings.simplefilter("error")
    # Warm-up: loads cached Numba kernels and SciPy code paths.
    warmup_start = time.perf_counter()
    gamma = pymedphys.gamma(ref_axes, ref, eval_axes, ev, **options)
    warmup_seconds = time.perf_counter() - warmup_start
    baseline = gamma.copy()
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        gamma = pymedphys.gamma(ref_axes, ref, eval_axes, ev, **options)
        times.append(time.perf_counter() - start)
        np.testing.assert_array_equal(gamma, baseline)
    np.save(sys.argv[4], gamma, allow_pickle=False)
    print(
        json.dumps(
            {
                "case": case,
                "shape": list(ref.shape),
                "options": options,
                "input_sha256": hashlib.sha256(b"".join(
                    array.tobytes() for array in (*ref_axes, ref, *eval_axes, ev)
                )).hexdigest(),
                "eligible_points": int(np.count_nonzero(ref >= 0.1 * ref.max())),
                "finite_points": int(np.isfinite(gamma).sum()),
                "pass_count": int(np.count_nonzero(gamma <= 1)),
                "max_gamma": float(np.nanmax(gamma)),
                "warmup_seconds": warmup_seconds,
                "times": times,
                "gamma_sum": float(np.nansum(gamma)),
                "nan_count": int(np.isnan(gamma).sum()),
                "points": int(np.size(gamma)),
                "origins": origins,
                "python": sys.version,
                "platform": platform.platform(),
                "processor": platform.processor(),
                "versions": {"numpy": np.__version__, "scipy": scipy.__version__, "numba": numba.__version__},
                "numba_threads": numba.get_num_threads(),
            }
        )
    )


if __name__ == "__main__":
    main()
'''


def machine_description():
    """Read a processor description without recording a hostname or user name."""
    import platform

    description = platform.processor()
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                description = winreg.QueryValueEx(key, "ProcessorNameString")[0]
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        try:
            description = next(
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            )
        except (OSError, StopIteration):
            pass
    elif sys.platform == "darwin":
        try:
            description = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return f"{description or platform.machine()}; {os.cpu_count()} logical CPUs"


def validate_result(result):
    """Refuse to plot incomplete, inconsistent or numerically unequal results."""
    records = result["records"]
    cases = list(result["times"])
    assert result["elementwise_equal"]
    assert cases and set(cases) <= set(CASES)
    assert len(records) == len(cases) * 2 * result["rounds"]
    assert all(record["elementwise_equal"] for record in records)
    assert len({json.dumps(r["versions"], sort_keys=True) for r in records}) == 1
    assert len({r["python"] for r in records}) == 1
    assert len({r["platform"] for r in records}) == 1
    revisions = []
    for version in ("previous", "current"):
        found = {r["revision"] for r in records if r["version"] == version}
        assert len(found) == 1
        revisions.extend(found)
    assert len(set(revisions)) == 2
    for case in cases:
        selected = [r for r in records if r["case"] == case]
        assert len({r["input_sha256"] for r in selected}) == 1
        assert len({r["gamma_sha256"] for r in selected}) == 1
        assert all(r["finite_points"] == r["eligible_points"] for r in selected)
        assert all(r["nan_count"] + r["finite_points"] == r["points"] for r in selected)
        for version in ("previous", "current"):
            by_version = [r for r in selected if r["version"] == version]
            assert sorted(r["round"] for r in by_version) == list(
                range(result["rounds"])
            )
            times = [t for r in by_version for t in r["times"]]
            assert len(times) == result["rounds"] * result["repeats"]
            assert np.isfinite(times).all() and np.all(np.array(times) > 0)
            assert all(r["numba_threads"] == result["threads"] for r in by_version)
            np.testing.assert_array_equal(times, result["times"][case][version])


def save_comparison(result, output):
    """Save raw evidence, an exact-value table and a shareable comparison figure."""
    import csv
    import textwrap

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    validate_result(result)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    cases = list(result["times"])
    medians = {
        case: {
            v: float(np.median(result["times"][case][v]))
            for v in ("previous", "current")
        }
        for case in cases
    }
    with (output / "timings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case", "version", "revision", "round", "repeat", "seconds"])
        for record in result["records"]:
            for repeat, seconds in enumerate(record["times"], 1):
                writer.writerow(
                    [
                        record["case"],
                        record["version"],
                        record["revision"],
                        record["round"] + 1,
                        repeat,
                        seconds,
                    ]
                )
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "case",
                "previous_median_seconds",
                "current_median_seconds",
                "time_saved_percent",
                "speedup",
            ]
        )
        for case, values in medians.items():
            old, new = values["previous"], values["current"]
            writer.writerow([case, old, new, 100 * (1 - new / old), old / new])
            print(
                f"{case:14s} {old:8.3f} -> {new:8.3f} s; {100 * (1 - new / old):+6.1f}% time saved; {old / new:.2f}x speed-up"
            )

    labels = {
        "3d": "3% / 3 mm",
        "3d-maxgamma": "3% / 3 mm, cap 2",
        "3d-local": "2% / 2 mm, local",
        "3d-scipy": "3% / 3 mm, SciPy",
        "2d": "3% / 3 mm",
        "2d-scipy": "3% / 3 mm, SciPy",
    }
    colours = {"previous": "#B76121", "current": "#176B91"}
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    fig = plt.figure(figsize=(11, 9), facecolor="white")
    grid = fig.add_gridspec(
        2, 2, left=0.23, right=0.96, bottom=0.22, top=0.86, hspace=0.65, wspace=0.9
    )

    def bars(ax, selected, title):
        if not selected:
            ax.axis("off")
            return
        longest = max(max(result["times"][c][v]) for c in selected for v in colours)
        for version, offset, hatch in [
            ("previous", -0.18, "//"),
            ("current", 0.18, None),
        ]:
            for index, case in enumerate(selected):
                value = medians[case][version]
                times = result["times"][case][version]
                position = index + offset
                ax.barh(
                    position,
                    value,
                    0.32,
                    color=colours[version],
                    hatch=hatch,
                    label=version.capitalize() if index == 0 else None,
                )
                ax.plot(
                    [min(times), max(times)],
                    [position, position],
                    color="#222222",
                    lw=1,
                )
                ax.text(
                    max(times) + longest * 0.02,
                    position,
                    f"{value:.3f}",
                    va="center",
                    fontsize=9,
                )
        ax.set(
            yticks=range(len(selected)),
            yticklabels=[labels[c] for c in selected],
            xlim=(0, longest * 1.3),
            xlabel="Gamma-call time (s)",
            title=title,
        )
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.15)
        ax.set_axisbelow(True)

    left = fig.add_subplot(grid[0, 0])
    bars(left, [c for c in cases if c.startswith("3d")], "3D: 41 × 57 × 57")
    bars(
        fig.add_subplot(grid[0, 1]),
        [c for c in cases if c.startswith("2d")],
        "2D: 401 × 401",
    )
    handles, names = left.get_legend_handles_labels()
    if not handles:
        handles, names = fig.axes[-1].get_legend_handles_labels()
    fig.legend(
        handles,
        names,
        loc="upper center",
        bbox_to_anchor=(0.55, 0.922),
        ncol=2,
        frameon=False,
    )
    ax = fig.add_subplot(grid[1, :])
    ratios = []
    for index, case in enumerate(cases):
        round_ratios = []
        for round_index in range(result["rounds"]):
            pair = {
                v: next(
                    r
                    for r in result["records"]
                    if r["case"] == case
                    and r["version"] == v
                    and r["round"] == round_index
                )
                for v in colours
            }
            round_ratios.append(
                np.median(pair["current"]["times"])
                / np.median(pair["previous"]["times"])
            )
        ratio = medians[case]["current"] / medians[case]["previous"]
        ratios.extend([ratio, *round_ratios])
        ax.scatter(
            round_ratios,
            np.full(len(round_ratios), index),
            marker="|",
            s=120,
            color="#777777",
            label="Individual paired rounds" if index == 0 else None,
            zorder=3,
        )
        ax.scatter(
            ratio,
            index,
            marker="D",
            s=55,
            color=colours["current"],
            label="Ratio of overall medians" if index == 0 else None,
            zorder=4,
        )
        ax.annotate(
            f"{100 * (1 - ratio):+.1f}% time saved",
            (max(ratio, *round_ratios), index),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    ax.axvline(1, color="#555555", linestyle="--", linewidth=1)
    ax.set(
        yticks=range(len(cases)),
        yticklabels=[f"{c[:2].upper()} · {labels[c]}" for c in cases],
        xlim=(max(0, min(ratios) - 0.1), max(1, max(ratios)) + 0.35),
        xlabel="Current / previous time — lower is faster; 1 = equal time",
        title="Relative runtime, with variation between rounds",
    )
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.15)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    fig.suptitle(
        "PyMedPhys gamma: old vs new", x=0.55, y=0.99, fontsize=19, fontweight="bold"
    )
    fig.text(
        0.55,
        0.94,
        "Same inputs and criteria · exact full-array agreement in every measured case",
        ha="center",
        fontsize=11,
    )
    revisions = {
        v: next(r["revision"] for r in result["records"] if r["version"] == v)
        for v in colours
    }
    first = result["records"][0]
    footer = [
        f"Previous {revisions['previous']}  |  Current {revisions['current']}",
        f"{result.get('hardware', first['processor'])} | {first['platform']} | {result['threads']} Numba threads",
        f"Python {first['python'].split()[0]} | NumPy {first['versions']['numpy']} | SciPy {first['versions']['scipy']} | Numba {first['versions']['numba']}",
        f"{result.get('measured_at_utc', '')[:10]} UTC | {result['rounds']} alternating rounds × {result['repeats']} warmed timed calls/version/case; imports and compilation excluded.",
        "Bars: median and observed min–max (not confidence intervals). Synthetic grids; 10% cutoff; interpolation fraction 10.",
    ]
    fig.text(
        0.03,
        0.025,
        "\n".join(textwrap.fill(line, 132) for line in footer),
        va="bottom",
        fontsize=8,
        color="#444444",
    )
    fig.savefig(output / "comparison.png", dpi=200, facecolor="white")
    fig.savefig(output / "comparison.svg", facecolor="white")
    plt.close(fig)
    print(
        f"Saved comparison.png, comparison.svg, results.json, timings.csv and summary.csv in {output.resolve()}"
    )


def main():
    import argparse
    import datetime

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Local repository; defaults to the working directory",
    )
    parser.add_argument(
        "--previous-ref",
        default="866f83edad8586a42a739094e488f45242b72c95",
        help="Previous Git revision; default is the original benchmark baseline",
    )
    parser.add_argument(
        "--current-ref",
        default="HEAD",
        help="Current Git revision, default HEAD (committed code)",
    )
    parser.add_argument(
        "--threads", type=int, default=2, help="Numba threads per worker (default: 2)"
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    parser.add_argument(
        "--output",
        type=Path,
        help="New output directory; default gamma-performance-UTC_TIMESTAMP in the working directory",
    )
    parser.add_argument(
        "--plot-only",
        type=Path,
        metavar="RESULTS_JSON",
        help="Replot saved results without running gamma",
    )
    args = parser.parse_args()
    if min(args.threads, args.rounds, args.repeats) < 1:
        parser.error("Threads, rounds and repeats must be positive")
    if len(set(args.cases)) != len(args.cases):
        parser.error("Cases must not be repeated")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    output = (args.output or Path(f"gamma-performance-{timestamp}")).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if args.plot_only:
        save_comparison(json.loads(args.plot_only.read_text(encoding="utf-8")), output)
        return
    repo = args.repo.resolve(strict=True)

    def git(*arguments):
        return subprocess.check_output(
            ["git", "-C", str(repo), *arguments], text=True, stderr=subprocess.STDOUT
        ).strip()

    revisions = {
        "previous": git("rev-parse", "--verify", f"{args.previous_ref}^{{commit}}"),
        "current": git("rev-parse", "--verify", f"{args.current_ref}^{{commit}}"),
    }
    if revisions["previous"] == revisions["current"]:
        parser.error("Choose two different revisions")
    for version, revision in revisions.items():
        print(f"{version.capitalize()}: {revision}", flush=True)
    print(
        "Benchmarking committed revisions in temporary worktrees; your working files are preserved.",
        flush=True,
    )
    print(
        f"{machine_description()}; {args.threads} Numba threads. Results: {output}",
        flush=True,
    )
    # The temporary checkouts are created by this invocation and contain no user work.
    with tempfile.TemporaryDirectory(prefix="pymedphys-gamma-") as directory:
        roots = {}
        try:
            for version, revision in revisions.items():
                root = Path(directory) / version
                git("worktree", "add", "--detach", str(root), revision)
                roots[version] = root
            result = run_benchmark(
                roots["previous"],
                revisions["previous"],
                roots["current"],
                revisions["current"],
                cases=args.cases,
                rounds=args.rounds,
                repeats=args.repeats,
                threads=args.threads,
                progress_path=output / "progress.json",
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Benchmark command failed. No comparison chart was accepted.\n{error.stdout}\n{error.stderr}"
            ) from error
        finally:
            for root in roots.values():
                # --force permits generated Python/Numba caches, only in our new checkout.
                if not root.resolve().is_relative_to(Path(directory).resolve()):
                    raise RuntimeError(
                        "Refusing to remove a worktree outside this run's temporary directory"
                    )
                git("worktree", "remove", "--force", str(root))
    result["measured_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result["hardware"] = machine_description()
    save_comparison(result, output)


if __name__ == "__main__":
    main()
