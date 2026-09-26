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

"""Check a built sdist and wheel before they are published, or after.

Before publishing, pass the directory holding the build. The contents check
needs nothing beyond the standard library. The smoke test installs the wheel
into a fresh virtual environment, separate from any development environment,
so it exercises what a user would install.

Build the wheel from the sdist (plain ``uv build`` does this) so that a file
missing from the sdist also breaks the wheel, rather than being hidden by a
wheel built straight from the source tree.

After publishing, pass ``--published VERSION``. The wheel and the sdist are
resolved from PyPI's JSON Simple API and each exact archive URL is installed
into its own fresh environment, with pip's configuration and cache disabled
and the sdist forced to build, so no other index can substitute either file.
pip's installation report must show the expected file from PyPI's file host,
and each environment then gets the smoke test's import and CLI checks and
``pip check``. The environments use the Python running this script.

With ``--tests``, the wheel's environment then gains the ``user`` and ``tests``
extras, resolved afresh from PyPI as a user's installation would be, and runs
``pymedphys dev tests``. ``--summary FILE`` appends a Markdown report of every
result to FILE, for the job summary or the release pull request.
"""

import argparse
import dataclasses
import datetime
import email.parser
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import venv
import zipfile
from collections.abc import Callable, Mapping, Sequence
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
# The docs preparation command copies these three root-level documents.
REQUIRED_SDIST_FILES = (
    "pyproject.toml",
    "README.rst",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "PKG-INFO",
)
SDIST_PACKAGE_ROOT = "lib/pymedphys/"
WHEEL_PACKAGE_ROOT = "pymedphys/"
# Independent release expectations: keep these in sync with the project's
# license and license-files settings in pyproject.toml. Reading expectations
# from archive metadata would let matching omissions in both archives pass.
EXPECTED_LICENCE_EXPRESSION = "Apache-2.0 AND MIT"
EXPECTED_LICENCE_FILES = frozenset(("LICENSE", "lib/pymedphys/_pinnacle/LICENSE-MIT"))
# pymedphys.cli imports every command module, as the console script does.
SMOKE_IMPORTS = ("pymedphys", "pymedphys.dicom", "pymedphys.cli")
# The extras and command a contributor uses to run the default test selection.
TEST_EXTRAS = ("user", "tests")
TEST_COMMAND = ("-m", "pymedphys", "dev", "tests")

IMPORT_CHECK = """\
import importlib
import sys
from pathlib import Path

environment = Path(sys.prefix).resolve()
for name in ("pymedphys._version", *sys.argv[1:]):
    module = importlib.import_module(name)
    source = Path(module.__file__).resolve()
    if not source.is_relative_to(environment):
        raise RuntimeError(f"{name} was imported from {source}, outside {environment}")

import pymedphys
print(pymedphys.__version__)
"""


# pip's --report locates the archive it installed. PyPI serves files from a
# separate host, so an index URL is not a valid download URL. The tests
# substitute a local index.
@dataclasses.dataclass(frozen=True)
class PackageIndex:
    project_url: str
    files_url: str
    dependency_index_url: str = "https://pypi.org/simple/"


PYPI = PackageIndex(
    project_url="https://pypi.org/simple/pymedphys/",
    files_url="https://files.pythonhosted.org/",
)
FORMATS = ("wheel", "sdist")
RETRY_INTERVAL = 30
# Keep explicit transport settings for institutional proxies and slow links.
# Other pip settings could change package sources or installation locations.
PIP_NETWORK_SETTINGS = frozenset(
    {
        "PIP_CERT",
        "PIP_CLIENT_CERT",
        "PIP_PROXY",
        "PIP_TIMEOUT",
        "PIP_DEFAULT_TIMEOUT",
        "PIP_RETRIES",
        "PIP_RESUME_RETRIES",
    }
)


@dataclasses.dataclass
class CheckResult:
    """One published-file check: the wheel, the sdist, or the test suite."""

    name: str
    filename: str = ""
    sha256: str = ""
    failures: list[str] = dataclasses.field(default_factory=list)
    ran: bool = True

    @property
    def status(self) -> str:
        if not self.ran:
            return "not run"
        return "failed" if self.failures else "passed"


@dataclasses.dataclass(frozen=True)
class Distributions:
    sdist: Path
    wheel: Path


@dataclasses.dataclass(frozen=True)
class Archive:
    """A distribution's metadata and its member paths, relative to its root.

    ``licence_root`` is where the files named by ``License-File`` live: the
    sdist root, or the wheel's ``.dist-info/licenses/`` directory.
    """

    version: str
    files: frozenset[str]
    licence_expression: str | None = None
    licence_files: tuple[str, ...] = ()
    licence_root: str = ""


@dataclasses.dataclass(frozen=True)
class _Metadata:
    version: str
    licence_expression: str | None
    licence_files: tuple[str, ...]


def find_distributions(dist_dir: Path) -> Distributions:
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        raise ValueError(
            f"Expected exactly one sdist and one wheel in {dist_dir}, found "
            f"{[p.name for p in sdists]} and {[p.name for p in wheels]}"
        )

    return Distributions(sdist=sdists[0], wheel=wheels[0])


def _parse_metadata(text: str) -> _Metadata:
    message = email.parser.Parser().parsestr(text, headersonly=True)
    version = message["Version"]
    if not version:
        raise ValueError("Distribution metadata has no Version field")

    return _Metadata(
        version=version,
        licence_expression=message["License-Expression"],
        licence_files=tuple(message.get_all("License-File") or ()),
    )


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
        metadata = _parse_metadata(pkg_info.read().decode("utf-8"))

    files = frozenset(name.split("/", 1)[1] for name in names if "/" in name)
    return Archive(
        version=metadata.version,
        files=files,
        licence_expression=metadata.licence_expression,
        licence_files=metadata.licence_files,
    )


def read_wheel(path: Path) -> Archive:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        metadata_paths = [
            name
            for name in names
            if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError(f"{path.name} does not have exactly one METADATA")
        (metadata_path,) = metadata_paths
        metadata = _parse_metadata(archive.read(metadata_path).decode("utf-8"))

    dist_info = metadata_path.split("/", 1)[0]
    return Archive(
        version=metadata.version,
        files=frozenset(names),
        licence_expression=metadata.licence_expression,
        licence_files=metadata.licence_files,
        licence_root=f"{dist_info}/licenses/",
    )


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

    for kind, archive in (("sdist", sdist), ("wheel", wheel)):
        # PEP 639: a single SPDX expression that tools can read, rather than
        # the full licence text in the free-form License field.
        if not archive.licence_expression:
            failures.append(f"The {kind} metadata has no License-Expression")
        elif archive.licence_expression != EXPECTED_LICENCE_EXPRESSION:
            failures.append(
                f"The {kind} metadata License-Expression is "
                f"{archive.licence_expression!r}, expected "
                f"{EXPECTED_LICENCE_EXPRESSION!r}"
            )

        # Check declarations independently of file presence: losing a header
        # and its file together must not disable that file's validation.
        if set(archive.licence_files) != EXPECTED_LICENCE_FILES:
            failures.append(
                f"The {kind} metadata License-File declarations are "
                f"{sorted(set(archive.licence_files))!r}, expected "
                f"{sorted(EXPECTED_LICENCE_FILES)!r}"
            )
        missing_licences = [
            name
            for name in archive.licence_files
            if archive.licence_root + name not in archive.files
        ]
        if missing_licences:
            failures.append(
                f"The {kind} is missing the licence files its metadata names: "
                f"{', '.join(missing_licences)}"
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


def _child_environment() -> dict[str, str]:
    # A venv and python -I do not isolate pip's configuration. Control it for
    # every child, including the pip subprocesses that install build tools.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}
        and (not key.upper().startswith("PIP_") or key.upper() in PIP_NETWORK_SETTINGS)
    }
    # This disables global, user, and per-environment pip configuration files.
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def _run(
    command: Sequence[str | os.PathLike[str]], *, cwd: Path
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [os.fspath(item) for item in command],
        cwd=cwd,
        env=_child_environment(),
        capture_output=True,
        text=True,
        # The children run with -I, which ignores PYTHONIOENCODING, so decode
        # their output leniently rather than crash on an unexpected byte.
        errors="replace",
        check=False,
    )


def _run_to_log(
    command: Sequence[str | os.PathLike[str]], *, cwd: Path, log: Path, bin_dir: Path
) -> int:
    """Run a long command with its output written to ``log`` as it arrives."""
    environment = _child_environment()
    # Tests can spawn console scripts by name, so prefer this environment.
    environment["PATH"] = os.pathsep.join(
        (os.fspath(bin_dir), environment.get("PATH", os.defpath))
    )
    with log.open("wb") as output:
        return subprocess.run(
            [os.fspath(item) for item in command],
            cwd=cwd,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.rstrip().splitlines()[-lines:])


def _create_environment(env_dir: Path) -> Path:
    """Create a virtual environment with pip and return its scripts directory."""
    venv.create(env_dir, with_pip=True)
    return env_dir / ("Scripts" if os.name == "nt" else "bin")


def _executable(bin_dir: Path, name: str) -> Path:
    return bin_dir / (f"{name}.exe" if os.name == "nt" else name)


def _check_environment(
    bin_dir: Path,
    expected_version: str,
    *,
    imports: Sequence[str],
    working_directory: Path,
    pip_check: bool = False,
) -> list[str]:
    """Check an installed pymedphys's imports, version, and CLI."""
    failures = []
    python = _executable(bin_dir, "python")

    check_imports = _run(
        [python, "-I", "-c", IMPORT_CHECK, *imports],
        cwd=working_directory,
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

    cli = _run([_executable(bin_dir, "pymedphys"), "--version"], cwd=working_directory)
    expected_output = f"pymedphys {expected_version}"
    if cli.returncode != 0 or cli.stdout.strip() != expected_output:
        failures.append(
            f"pymedphys --version exited {cli.returncode} and printed "
            f"{cli.stdout.strip()[:200]!r}, expected {expected_output!r}"
        )

    if pip_check:
        dependencies = _run([python, "-I", "-m", "pip", "check"], cwd=working_directory)
        if dependencies.returncode != 0:
            failures.append(
                f"pip check found broken requirements:\n{dependencies.stdout}"
            )

    return failures


def smoke_test(
    wheel: Path,
    expected_version: str,
    *,
    imports: Sequence[str] = SMOKE_IMPORTS,
    pip_args: Sequence[str] = (),
) -> list[str]:
    """Install the wheel into a fresh venv and check its imports and CLI."""
    expected_version = _normalise_tag(expected_version)

    with tempfile.TemporaryDirectory(prefix="pymedphys-dist-check-") as env_dir:
        working_directory = Path(env_dir)
        bin_dir = _create_environment(working_directory)

        install = _run(
            [
                _executable(bin_dir, "python"),
                "-I",
                "-m",
                "pip",
                "install",
                "--quiet",
                *pip_args,
                wheel.resolve(),
            ],
            cwd=working_directory,
        )
        if install.returncode != 0:
            return [f"Installing {wheel.name} failed:\n{install.stderr}"]

        return _check_environment(
            bin_dir,
            expected_version,
            imports=imports,
            working_directory=working_directory,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def local_hashes(dist_dir: Path) -> dict[str, str]:
    """Map each distribution's filename to its SHA-256."""
    distributions = find_distributions(dist_dir)
    return {
        path.name: _sha256(path) for path in (distributions.wheel, distributions.sdist)
    }


def _report_sha256(download_info: Mapping) -> str | None:
    archive_info = download_info.get("archive_info", {})
    sha256 = archive_info.get("hashes", {}).get("sha256")
    if sha256 is None and archive_info.get("hash", "").startswith("sha256="):
        sha256 = archive_info["hash"].removeprefix("sha256=")
    return sha256


def _filename(url: str) -> str:
    return urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])


def _matches_distribution(filename: str, kind: str, version: str) -> bool:
    if kind == "wheel":
        return filename.startswith(f"pymedphys-{version}-") and filename.endswith(
            ".whl"
        )
    return filename == f"pymedphys-{version}.tar.gz"


def _published_url(
    index: PackageIndex,
    kind: str,
    version: str,
    *,
    wait: float,
    sleep: Callable[[float], None],
) -> str:
    """Select an exact archive from the index's JSON Simple API, with its hash."""
    request = urllib.request.Request(
        index.project_url,
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
    )
    deadline = time.monotonic() + wait
    while True:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                listing = json.load(response)
        except urllib.error.HTTPError as error:
            # Not yet listed, or a transient index error: retry within wait.
            if error.code != 404 and error.code != 429 and error.code < 500:
                raise
            listing = {"files": []}

        api_version = listing.get("meta", {}).get("api-version", "1.0")
        if api_version.split(".")[0] != "1":
            raise ValueError(f"Unsupported Simple API version: {api_version}")
        matches = [
            entry
            for entry in listing["files"]
            if _matches_distribution(entry["filename"], kind, version)
        ]
        if matches:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(
                f"The {kind} of pymedphys {version} is not available at "
                f"{index.project_url}"
            )
        print(f"The {kind} of pymedphys {version} is not available yet; retrying")
        sleep(min(RETRY_INTERVAL, remaining))

    if len(matches) != 1:
        raise ValueError(f"Expected one {kind} of pymedphys {version} on the index")
    (entry,) = matches
    url = urllib.parse.urljoin(index.project_url, entry["url"])
    if not url.startswith(index.files_url):
        raise ValueError(f"The index's file {url} is not served from {index.files_url}")
    filename = _filename(url)
    if filename != entry["filename"]:
        raise ValueError(f"The index's filename does not match its URL: {url}")
    sha256 = entry.get("hashes", {}).get("sha256", "")
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError(f"The index has no valid SHA-256 for {filename}")
    # pip checks the downloaded bytes against this hash before installing.
    return urllib.parse.urldefrag(url)[0] + f"#sha256={sha256}"


def _local_hash_mismatch(url: str, hashes: Mapping[str, str]) -> str | None:
    """Describe how the index's archive differs from the local copy, if it does."""
    location, fragment = urllib.parse.urldefrag(url)
    filename = _filename(location)
    sha256 = fragment.removeprefix("sha256=")
    expected_sha256 = hashes.get(filename)
    if expected_sha256 is None:
        return f"There is no local copy of {filename} to compare"
    if sha256 != expected_sha256:
        return (
            f"The published {filename} has SHA-256 {sha256}, but the local copy "
            f"has {expected_sha256}"
        )
    return None


def check_install_report(
    report: Mapping,
    kind: str,
    version: str,
    index: PackageIndex,
    *,
    local_hashes: Mapping[str, str] | None = None,
) -> list[str]:
    """Return a failure for each way the installed archive is not as published."""
    entries = [
        entry
        for entry in report.get("install", [])
        if entry["metadata"]["name"].lower() == "pymedphys"
    ]
    if len(entries) != 1:
        return [f"The {kind} installation report has no pymedphys entry"]
    (entry,) = entries

    failures = []
    installed_version = entry["metadata"]["version"]
    if installed_version != version:
        failures.append(
            f"The {kind} check installed pymedphys {installed_version}, "
            f"expected {version}"
        )

    url = entry["download_info"]["url"]
    filename = _filename(url)
    if not _matches_distribution(filename, kind, version):
        failures.append(f"The {kind} check installed {filename}, which is not a {kind}")
    if not url.startswith(index.files_url):
        failures.append(
            f"The {kind} check downloaded {url}, which is not served from "
            f"{index.files_url}"
        )

    if local_hashes is not None:
        expected_sha256 = local_hashes.get(filename)
        sha256 = _report_sha256(entry["download_info"])
        if expected_sha256 is None:
            failures.append(f"There is no local copy of {filename} to compare")
        elif sha256 != expected_sha256:
            failures.append(
                f"The published {filename} has SHA-256 {sha256}, but the local "
                f"copy has {expected_sha256}"
            )

    return failures


def _install_published_url(
    python: Path,
    kind: str,
    url: str,
    index: PackageIndex,
    *,
    report: Path,
    working_directory: Path,
) -> subprocess.CompletedProcess:
    """Install the selected archive; other indexes cannot substitute it."""
    command = [
        python,
        "-I",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--progress-bar=off",
        # A fresh environment cannot already satisfy the requirement, and no
        # cache means no previously built or downloaded wheel is reused.
        "--no-cache-dir",
        "--only-binary=pymedphys" if kind == "wheel" else "--no-binary=pymedphys",
        f"--index-url={index.dependency_index_url}",
        f"--report={report}",
        url,
    ]
    return _run(command, cwd=working_directory)


def _run_test_suite(
    python: Path,
    url: str,
    index: PackageIndex,
    *,
    report_dir: Path,
    working_directory: Path,
    test_command: Sequence[str] | None,
) -> list[str]:
    """Add the test extras to the wheel's environment and run the test suite.

    Requesting the extras on the same URL keeps pymedphys the published file;
    only the extras' dependencies come from the dependency index.
    """
    install_log = report_dir / "tests-install.log"
    requirement = f"pymedphys[{','.join(TEST_EXTRAS)}] @ {url}"
    install = _run(
        [
            python,
            "-I",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--progress-bar=off",
            "--no-cache-dir",
            f"--index-url={index.dependency_index_url}",
            requirement,
        ],
        cwd=working_directory,
    )
    install_log.write_text(install.stdout + install.stderr, encoding="utf-8")
    if install.returncode != 0:
        return [
            f"Installing the {' and '.join(TEST_EXTRAS)} extras for the test suite "
            f"failed; the log is {install_log}:\n{install.stderr[-2000:]}"
        ]

    log = report_dir / "tests.log"
    if test_command is None:
        junit = report_dir / "tests-junit.xml"
        test_command = (*TEST_COMMAND, f"--junitxml={junit}")
    print(f"Running the test suite; its output is written to {log}", flush=True)
    returncode = _run_to_log(
        [python, "-I", *test_command],
        cwd=working_directory,
        log=log,
        bin_dir=python.parent,
    )
    print(_tail(log.read_text(encoding="utf-8", errors="replace")), flush=True)
    if returncode != 0:
        return [f"The test suite failed with exit code {returncode}; the log is {log}"]
    return []


def check_published_files(
    version: str,
    index: PackageIndex,
    *,
    report_dir: Path,
    compare_with: Path | None = None,
    wait: float = 0,
    imports: Sequence[str] = SMOKE_IMPORTS,
    sleep: Callable[[float], None] = time.sleep,
    tests: bool = False,
    test_command: Sequence[str] | None = None,
) -> list[CheckResult]:
    """Install the published wheel and sdist separately and check each one.

    With ``tests``, the test suite then runs in the wheel's environment,
    unless the wheel's own checks failed.
    """
    version = _normalise_tag(version)
    hashes = local_hashes(compare_with) if compare_with is not None else None
    results = []
    suite = CheckResult("tests", ran=False)

    for kind in FORMATS:
        result = CheckResult(kind)
        results.append(result)
        report = report_dir / f"{kind}-install.json"
        log = report_dir / f"{kind}-install.log"
        try:
            url = _published_url(index, kind, version, wait=wait, sleep=sleep)
        except (OSError, ValueError) as error:
            message = f"Resolving the {kind} of pymedphys {version} failed: {error}"
            log.write_text(message + "\n", encoding="utf-8")
            result.failures.append(message)
            continue
        location, fragment = urllib.parse.urldefrag(url)
        result.filename = _filename(location)
        result.sha256 = fragment.removeprefix("sha256=")
        if kind == "wheel":
            suite.filename = result.filename
        # Reject a file that differs from the local copy before pip downloads
        # it or runs its build; the report check below confirms the install.
        if hashes is not None:
            mismatch = _local_hash_mismatch(url, hashes)
            if mismatch:
                log.write_text(mismatch + "\n", encoding="utf-8")
                result.failures.append(mismatch)
                continue
        with tempfile.TemporaryDirectory(prefix=f"pymedphys-{kind}-check-") as env:
            working_directory = Path(env)
            bin_dir = _create_environment(working_directory)
            python = _executable(bin_dir, "python")
            install = _install_published_url(
                python,
                kind,
                url,
                index,
                report=report,
                working_directory=working_directory,
            )
            log.write_text(install.stdout + install.stderr, encoding="utf-8")
            if install.returncode != 0:
                result.failures.append(
                    f"Installing the {kind} of pymedphys {version} failed; the "
                    f"log is {log}:\n{install.stderr[-2000:]}"
                )
                continue

            result.failures += check_install_report(
                json.loads(report.read_text(encoding="utf-8")),
                kind,
                version,
                index,
                local_hashes=hashes,
            )
            result.failures += _check_environment(
                bin_dir,
                version,
                imports=imports,
                working_directory=working_directory,
                pip_check=True,
            )
            if not result.failures:
                print(f"The {kind} passed. Installation report: {report}")
                if tests and kind == "wheel":
                    suite.ran = True
                    suite.failures = _run_test_suite(
                        python,
                        url,
                        index,
                        report_dir=report_dir,
                        working_directory=working_directory,
                        test_command=test_command,
                    )

    if tests:
        results.append(suite)
    return results


def check_published(
    version: str,
    index: PackageIndex,
    *,
    report_dir: Path,
    compare_with: Path | None = None,
    wait: float = 0,
    imports: Sequence[str] = SMOKE_IMPORTS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Return a failure message for each problem with the published files."""
    results = check_published_files(
        version,
        index,
        report_dir=report_dir,
        compare_with=compare_with,
        wait=wait,
        imports=imports,
        sleep=sleep,
    )
    return [failure for result in results for failure in result.failures]


def format_summary(
    version: str,
    results: Sequence[CheckResult],
    *,
    compare_with: Path | None = None,
) -> str:
    """Describe the published-file check in Markdown, one row per result."""
    outcome = "failed" if any(result.failures for result in results) else "passed"
    checked = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"### pymedphys {_normalise_tag(version)} from PyPI: {outcome}",
        "",
        f"Checked on {platform.platform()} with Python "
        f"{platform.python_version()} at {checked} UTC.",
    ]
    if compare_with is not None:
        lines.append(
            f"The published files had to match the copies in `{compare_with}`."
        )
    lines += ["", "| Check | File | SHA-256 | Result |", "| --- | --- | --- | --- |"]
    for result in results:
        name = "test suite" if result.name == "tests" else result.name
        filename = f"`{result.filename}`" if result.filename else "not resolved"
        if result.name == "tests":
            filename = "wheel environment"
        sha256 = f"`{result.sha256}`" if result.sha256 else ""
        lines.append(f"| {name} | {filename} | {sha256} | {result.status} |")

    failures = [failure for result in results for failure in result.failures]
    if failures:
        lines.append("")
        lines += [f"- {failure.splitlines()[0].rstrip(':')}" for failure in failures]
    return "\n".join(lines) + "\n\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "dist_dir",
        type=Path,
        nargs="?",
        help="Directory holding the build to check before publishing",
    )
    parser.add_argument(
        "--expected-version",
        help="Version the distributions must carry; a leading v is ignored",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Check the archive contents only",
    )
    published = parser.add_argument_group("after publishing")
    published.add_argument(
        "--published",
        metavar="VERSION",
        help="Check this version on PyPI instead of a local build",
    )
    published.add_argument(
        "--compare-with",
        type=Path,
        metavar="DIST_DIR",
        help="Also require the published files to match the sdist and wheel here",
    )
    published.add_argument(
        "--report-dir",
        type=Path,
        help="Directory for pip's installation reports and logs (default: a new "
        "temporary directory)",
    )
    published.add_argument(
        "--wait",
        type=float,
        metavar="SECONDS",
        help="Keep retrying for this long while the version is not yet available",
    )
    published.add_argument(
        "--tests",
        action="store_true",
        help="Also install the wheel's user and tests extras and run the test "
        "suite in its environment",
    )
    published.add_argument(
        "--summary",
        type=Path,
        metavar="FILE",
        help="Append a Markdown report of the results to FILE",
    )
    args = parser.parse_args(argv)

    if args.published is None:
        if args.dist_dir is None:
            parser.error("give a build directory or --published VERSION")
        published_only = {
            "--compare-with": args.compare_with,
            "--report-dir": args.report_dir,
            "--wait": args.wait,
            "--tests": args.tests or None,
            "--summary": args.summary,
        }
        for option, value in published_only.items():
            if value is not None:
                parser.error(f"{option} applies only with --published")
        failures = check_build(args.dist_dir, args.expected_version, args.skip_install)
    else:
        if args.dist_dir is not None:
            parser.error("--published checks PyPI, not a build directory")
        if args.expected_version is not None or args.skip_install:
            parser.error(
                "--expected-version and --skip-install apply only to a build "
                "directory"
            )
        report_dir = args.report_dir or Path(
            tempfile.mkdtemp(prefix="pymedphys-published-")
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        print(f"Installation reports and logs: {report_dir.resolve()}")
        results = check_published_files(
            args.published,
            PYPI,
            report_dir=report_dir.resolve(),
            compare_with=args.compare_with,
            wait=args.wait or 0,
            tests=args.tests,
        )
        failures = [failure for result in results for failure in result.failures]
        if args.summary is not None:
            with args.summary.open("a", encoding="utf-8") as summary:
                summary.write(
                    format_summary(
                        args.published,
                        results,
                        compare_with=args.compare_with,
                    )
                )

    for failure in failures:
        print(f"::error::{failure}")
    if not failures:
        print("The distributions passed every check.")

    return 1 if failures else 0


def check_filenames(
    distributions: Distributions, sdist: Archive, wheel: Archive
) -> list[str]:
    """Require the metadata version to be the canonical one in the filenames.

    The build copies the version from pyproject.toml into the metadata
    unchanged but names the files with its canonical form, so a non-canonical
    version would pass the tag check and then disagree with its own filenames.
    """
    filename_versions = (
        (
            "sdist",
            distributions.sdist.name,
            sdist,
            distributions.sdist.name.removeprefix("pymedphys-").removesuffix(".tar.gz"),
        ),
        (
            "wheel",
            distributions.wheel.name,
            wheel,
            distributions.wheel.name.removeprefix("pymedphys-").split("-")[0],
        ),
    )
    return [
        f"The {kind} metadata version {archive.version!r} is not the canonical "
        f"{filename_version!r} in its filename {filename}. Write the version in "
        "pyproject.toml in canonical PEP 440 form."
        for kind, filename, archive, filename_version in filename_versions
        if archive.version != filename_version
    ]


def check_build(
    dist_dir: Path, expected_version: str | None, skip_install: bool
) -> list[str]:
    distributions = find_distributions(dist_dir)
    sdist = read_sdist(distributions.sdist)
    wheel = read_wheel(distributions.wheel)
    print(
        f"{distributions.sdist.name}: {len(sdist.files)} files; "
        f"{distributions.wheel.name}: {len(wheel.files)} files"
    )

    failures = check_contents(sdist, wheel, expected_version)
    failures += check_filenames(distributions, sdist, wheel)
    if not failures and not skip_install:
        failures = smoke_test(distributions.wheel, wheel.version)

    return failures


if __name__ == "__main__":
    sys.exit(main())
