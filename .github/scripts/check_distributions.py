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

"""Check a built sdist and wheel before they are published.

The contents check needs nothing beyond the standard library. The smoke test
installs the wheel into a fresh virtual environment, separate from any
development environment, so it exercises what a user would install.

Build the wheel from the sdist (plain ``uv build`` does this) so that a file
missing from the sdist also breaks the wheel, rather than being hidden by a
wheel built straight from the source tree.
"""

import argparse
import dataclasses
import email.parser
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from collections.abc import Sequence
from pathlib import Path

# Relative to the package root: ``pymedphys/`` in the wheel and
# ``lib/pymedphys/`` in the sdist.
REQUIRED_PACKAGE_FILES = (
    "__init__.py",
    "__main__.py",
    "_version.py",
    "_data/hashes.json",
    "_data/urls.json",
)
REQUIRED_SDIST_FILES = ("pyproject.toml", "README.rst", "LICENSE", "PKG-INFO")
SDIST_PACKAGE_ROOT = "lib/pymedphys/"
WHEEL_PACKAGE_ROOT = "pymedphys/"
# pymedphys.cli imports every command module, as the console script does.
SMOKE_IMPORTS = ("pymedphys", "pymedphys.dicom", "pymedphys.cli")


@dataclasses.dataclass(frozen=True)
class Distributions:
    sdist: Path
    wheel: Path


@dataclasses.dataclass(frozen=True)
class Archive:
    """A distribution's version and its member paths, relative to its root."""

    version: str
    files: frozenset[str]


def find_distributions(dist_dir: Path) -> Distributions:
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        raise ValueError(
            f"Expected exactly one sdist and one wheel in {dist_dir}, found "
            f"{[p.name for p in sdists]} and {[p.name for p in wheels]}"
        )

    return Distributions(sdist=sdists[0], wheel=wheels[0])


def _version_from_metadata(text: str) -> str:
    version = email.parser.Parser().parsestr(text, headersonly=True)["Version"]
    if not version:
        raise ValueError("Distribution metadata has no Version field")

    return version


def read_sdist(path: Path) -> Archive:
    with tarfile.open(path, "r:gz") as archive:
        names = [member.name for member in archive.getmembers() if member.isfile()]
        roots = {name.split("/", 1)[0] for name in names}
        if len(roots) != 1:
            raise ValueError(f"{path.name} does not have a single top directory")
        (root,) = roots

        pkg_info = archive.extractfile(f"{root}/PKG-INFO")
        if pkg_info is None:
            raise ValueError(f"{path.name} has no PKG-INFO")
        version = _version_from_metadata(pkg_info.read().decode("utf-8"))

    files = frozenset(name.split("/", 1)[1] for name in names if "/" in name)
    return Archive(version=version, files=files)


def read_wheel(path: Path) -> Archive:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        metadata = [
            name
            for name in names
            if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
        ]
        if len(metadata) != 1:
            raise ValueError(f"{path.name} does not have exactly one METADATA")
        version = _version_from_metadata(archive.read(metadata[0]).decode("utf-8"))

    return Archive(version=version, files=frozenset(names))


def _normalise_tag(version: str) -> str:
    return version[1:] if version.startswith("v") else version


def check_contents(
    sdist: Archive, wheel: Archive, expected_version: str | None = None
) -> list[str]:
    """Return a failure message for each problem with the built contents."""
    failures = []

    if sdist.version != wheel.version:
        failures.append(
            f"The sdist and wheel versions differ: {sdist.version} and {wheel.version}"
        )
    if expected_version is not None:
        expected = _normalise_tag(expected_version)
        for kind, archive in (("sdist", sdist), ("wheel", wheel)):
            if archive.version != expected:
                failures.append(
                    f"The {kind} is version {archive.version}, expected {expected}. "
                    "The release tag must be v followed by the version in "
                    "pyproject.toml."
                )

    missing_from_sdist = [
        name
        for name in REQUIRED_SDIST_FILES
        + tuple(SDIST_PACKAGE_ROOT + f for f in REQUIRED_PACKAGE_FILES)
        if name not in sdist.files
    ]
    if missing_from_sdist:
        failures.append(f"The sdist is missing {', '.join(missing_from_sdist)}")

    missing_from_wheel = [
        WHEEL_PACKAGE_ROOT + name
        for name in REQUIRED_PACKAGE_FILES
        if WHEEL_PACKAGE_ROOT + name not in wheel.files
    ]
    if missing_from_wheel:
        failures.append(f"The wheel is missing {', '.join(missing_from_wheel)}")

    # Every packaged file must also be in the sdist, or a wheel rebuilt from
    # the sdist (as conda-forge and Linux distributions do) would lack it.
    # Skip this when the sdist has no package at all: that is reported above.
    if not missing_from_sdist:
        not_in_sdist = sorted(
            name
            for name in wheel.files
            if name.startswith(WHEEL_PACKAGE_ROOT)
            and SDIST_PACKAGE_ROOT + name[len(WHEEL_PACKAGE_ROOT) :] not in sdist.files
        )
        if not_in_sdist:
            shown = ", ".join(not_in_sdist[:10])
            more = len(not_in_sdist) - 10
            suffix = f" and {more} more" if more > 0 else ""
            failures.append(
                f"{len(not_in_sdist)} wheel files are not in the sdist: {shown}{suffix}"
            )

    return failures


def _run(command: Sequence[str | os.PathLike[str]]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [os.fspath(item) for item in command],
        capture_output=True,
        text=True,
        check=False,
    )


def smoke_test(
    wheel: Path,
    expected_version: str,
    *,
    imports: Sequence[str] = SMOKE_IMPORTS,
    pip_args: Sequence[str] = (),
) -> list[str]:
    """Install the wheel into a fresh venv and check its imports and CLI."""
    failures = []
    expected_version = _normalise_tag(expected_version)

    with tempfile.TemporaryDirectory(prefix="pymedphys-dist-check-") as env_dir:
        venv.create(env_dir, with_pip=True)
        bin_dir = Path(env_dir, "Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"

        install = _run(
            [python, "-m", "pip", "install", "--quiet", *pip_args, wheel.resolve()]
        )
        if install.returncode != 0:
            return [f"Installing {wheel.name} failed:\n{install.stderr}"]

        check_imports = _run(
            [
                python,
                "-c",
                "import importlib, sys\n"
                "for name in sys.argv[1:]:\n"
                "    importlib.import_module(name)\n"
                "import pymedphys\n"
                "print(pymedphys.__version__)",
                *imports,
            ]
        )
        if check_imports.returncode != 0:
            failures.append(
                f"Importing {', '.join(imports)} failed:\n{check_imports.stderr}"
            )
        elif check_imports.stdout.strip() != expected_version:
            failures.append(
                f"pymedphys.__version__ is {check_imports.stdout.strip()!r}, "
                f"expected {expected_version!r}"
            )

        cli = _run([bin_dir / "pymedphys", "--version"])
        expected_output = f"pymedphys {expected_version}"
        if cli.returncode != 0 or cli.stdout.strip() != expected_output:
            failures.append(
                f"pymedphys --version exited {cli.returncode} and printed "
                f"{cli.stdout.strip()[:200]!r}, expected {expected_output!r}"
            )

    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist_dir", type=Path, help="Directory holding the build")
    parser.add_argument(
        "--expected-version",
        help="Version the distributions must carry; a leading v is ignored",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Check the archive contents only",
    )
    args = parser.parse_args(argv)

    distributions = find_distributions(args.dist_dir)
    sdist = read_sdist(distributions.sdist)
    wheel = read_wheel(distributions.wheel)
    print(
        f"{distributions.sdist.name}: {len(sdist.files)} files; "
        f"{distributions.wheel.name}: {len(wheel.files)} files"
    )

    failures = check_contents(sdist, wheel, args.expected_version)
    if not failures and not args.skip_install:
        failures = smoke_test(distributions.wheel, wheel.version)

    for failure in failures:
        print(f"::error::{failure}")
    if not failures:
        print("The distributions passed every check.")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
