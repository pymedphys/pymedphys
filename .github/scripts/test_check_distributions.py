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

"""Tests for the distribution checks, on synthetic archives and a local index."""

import base64
import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from check_distributions import (
    PackageIndex,
    check_contents,
    check_install_report,
    check_published,
    find_distributions,
    read_sdist,
    read_wheel,
    smoke_test,
)

VERSION = "1.2.0.dev0"

PACKAGE_FILES = {
    "__init__.py": "from ._version import __version__\n",
    "__main__.py": textwrap.dedent(
        """\
        import sys

        from . import __version__


        def main():
            if sys.argv[1:] == ["--version"]:
                print(f"pymedphys {__version__}")
            else:
                sys.exit(2)
        """
    ),
    "_version.py": f'__version__ = "{VERSION}"\n',
    "_data/hashes.json": "{}\n",
    "_data/urls.json": "{}\n",
    "dicom.py": "",
    "cli.py": "",
}


# An in-tree PEP 517 backend with no build requirements, so pip can build a
# wheel from the synthetic sdist without network access.
BUILDABLE_PYPROJECT = textwrap.dedent(
    """\
    [build-system]
    requires = []
    build-backend = "backend"
    backend-path = ["."]
    """
)
BUILD_BACKEND = textwrap.dedent(
    """\
    import base64
    import hashlib
    import zipfile
    from pathlib import Path


    def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
        metadata = Path("PKG-INFO").read_text(encoding="utf-8")
        (version,) = (
            line.removeprefix("Version: ")
            for line in metadata.splitlines()
            if line.startswith("Version: ")
        )
        dist_info = f"pymedphys-{version}.dist-info"
        files = {
            f"pymedphys/{path.relative_to('lib/pymedphys').as_posix()}": path.read_bytes()
            for path in Path("lib/pymedphys").rglob("*")
            if path.is_file()
        }
        files[f"{dist_info}/METADATA"] = metadata.encode()
        files[f"{dist_info}/WHEEL"] = (
            b"Wheel-Version: 1.0\\nGenerator: test\\nRoot-Is-Purelib: true\\n"
            b"Tag: py3-none-any\\n"
        )
        files[f"{dist_info}/entry_points.txt"] = (
            b"[console_scripts]\\npymedphys = pymedphys.__main__:main\\n"
        )
        record = []
        for name, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            record.append(f"{name},sha256={digest.rstrip(b'=').decode()},{len(data)}")
        record.append(f"{dist_info}/RECORD,,")
        files[f"{dist_info}/RECORD"] = ("\\n".join(record) + "\\n").encode()

        filename = f"pymedphys-{version}-py3-none-any.whl"
        with zipfile.ZipFile(Path(wheel_directory, filename), "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return filename
    """
)


def _metadata(version):
    return f"Metadata-Version: 2.4\nName: pymedphys\nVersion: {version}\n"


def _write_sdist(
    directory, version=VERSION, package_files=PACKAGE_FILES, *, omit=(), buildable=False
):
    root = f"pymedphys-{version}"
    files = {
        "PKG-INFO": _metadata(version),
        "pyproject.toml": BUILDABLE_PYPROJECT if buildable else "",
        "README.rst": "",
        "CHANGELOG.md": "",
        "CONTRIBUTING.md": "",
        "LICENSE": "",
    }
    files.update(
        {f"lib/pymedphys/{name}": text for name, text in package_files.items()}
    )
    if buildable:
        files["backend.py"] = BUILD_BACKEND

    path = Path(directory, f"{root}.tar.gz")
    with tarfile.open(path, "w:gz") as archive:
        for name, text in files.items():
            if name in omit:
                continue
            data = text.encode()
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    return path


def _write_checkout(directory, package_files=PACKAGE_FILES):
    checkout = Path(directory, "checkout")
    for name, text in package_files.items():
        path = checkout / "pymedphys" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return checkout.resolve()


def _record_line(name, data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"{name},sha256={digest.decode()},{len(data)}"


def _write_wheel(directory, version=VERSION, package_files=PACKAGE_FILES):
    dist_info = f"pymedphys-{version}.dist-info"
    files = {f"pymedphys/{name}": text for name, text in package_files.items()}
    files[f"{dist_info}/METADATA"] = _metadata(version)
    files[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    files[f"{dist_info}/entry_points.txt"] = (
        "[console_scripts]\npymedphys = pymedphys.__main__:main\n"
    )

    record = [_record_line(name, text.encode()) for name, text in files.items()]
    record.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = "\n".join(record) + "\n"

    path = Path(directory, f"pymedphys-{version}-py3-none-any.whl")
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)

    return path


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = self.temp_dir.name

    def _failures(self, sdist, wheel, expected_version=None):
        return check_contents(read_sdist(sdist), read_wheel(wheel), expected_version)

    def test_complete_distributions_pass(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory)

        self.assertEqual(self._failures(sdist, wheel, VERSION), [])

    def test_sdist_without_the_package_fails(self):
        # What hatchling built when a global include listed only the docs.
        sdist = _write_sdist(self.directory, package_files={})
        wheel = _write_wheel(self.directory)

        failures = self._failures(sdist, wheel)

        self.assertTrue(any("sdist is missing" in f for f in failures), failures)
        self.assertTrue(any("lib/pymedphys/__init__.py" in f for f in failures))

    def test_wheel_file_missing_from_the_sdist_fails(self):
        partial = {k: v for k, v in PACKAGE_FILES.items() if k != "cli.py"}
        sdist = _write_sdist(self.directory, package_files=partial)
        wheel = _write_wheel(self.directory)

        failures = self._failures(sdist, wheel)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("cli.py", failures[0])

    def test_wheel_without_package_data_fails(self):
        partial = {k: v for k, v in PACKAGE_FILES.items() if k != "_data/hashes.json"}
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory, package_files=partial)

        failures = self._failures(sdist, wheel)

        self.assertTrue(any("pymedphys/_data/hashes.json" in f for f in failures))

    def test_sdist_requires_the_documentation_source_files(self):
        wheel = _write_wheel(self.directory)
        for name in ("README.rst", "CHANGELOG.md", "CONTRIBUTING.md"):
            with self.subTest(filename=name):
                sdist = _write_sdist(self.directory, omit=(name,))

                failures = self._failures(sdist, wheel)

                self.assertTrue(any(name in failure for failure in failures), failures)

    def test_sdist_and_wheel_versions_must_agree(self):
        sdist = _write_sdist(self.directory, version="1.2.0")
        wheel = _write_wheel(self.directory)

        failures = self._failures(sdist, wheel)

        self.assertTrue(any("versions differ" in f for f in failures), failures)

    def test_expected_version_accepts_a_leading_v(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory)

        self.assertEqual(self._failures(sdist, wheel, f"v{VERSION}"), [])

    def test_expected_version_mismatch_fails(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory)

        failures = self._failures(sdist, wheel, "v1.2.0")

        self.assertTrue(any("expected 1.2.0" in f for f in failures), failures)


class FindDistributionsTests(unittest.TestCase):
    def test_exactly_one_of_each_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "exactly one sdist"):
                find_distributions(Path(directory))

            _write_sdist(directory)
            wheel = _write_wheel(directory)

            self.assertEqual(find_distributions(Path(directory)).wheel, wheel)


class SmokeTestTests(unittest.TestCase):
    """Install a synthetic wheel into a fresh virtual environment, offline."""

    def test_installed_wheel_reports_its_version(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = _write_wheel(directory)

            failures = smoke_test(wheel, VERSION, pip_args=("--no-deps", "--no-index"))

        self.assertEqual(failures, [])

    def test_version_mismatch_is_reported(self):
        wrong = dict(PACKAGE_FILES, **{"_version.py": '__version__ = "0.0.0"\n'})
        with tempfile.TemporaryDirectory() as directory:
            wheel = _write_wheel(directory, package_files=wrong)

            failures = smoke_test(wheel, VERSION, pip_args=("--no-deps", "--no-index"))

        self.assertTrue(any("pymedphys --version" in f for f in failures), failures)
        self.assertTrue(any("__version__" in f for f in failures), failures)

    def test_checkout_cannot_hide_a_broken_wheel(self):
        broken = dict(PACKAGE_FILES, **{"_version.py": '__version__ = "0.0.0"\n'})
        del broken["dicom.py"]
        with tempfile.TemporaryDirectory() as directory:
            checkout = _write_checkout(directory)
            wheel = _write_wheel(directory, package_files=broken)
            original_cwd = Path.cwd()
            try:
                os.chdir(checkout)
                with mock.patch.dict(os.environ, {"PYTHONPATH": str(checkout)}):
                    failures = smoke_test(
                        wheel, VERSION, pip_args=("--no-deps", "--no-index")
                    )
            finally:
                os.chdir(original_cwd)

        self.assertTrue(
            any("Importing" in f and "pymedphys.dicom" in f for f in failures), failures
        )
        self.assertTrue(any("pymedphys --version" in f for f in failures), failures)

    def test_python_path_overrides_do_not_break_a_valid_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = _write_checkout(
                directory, {"__init__.py": 'raise RuntimeError("checkout imported")\n'}
            )
            wheel = _write_wheel(directory)
            with mock.patch.dict(
                os.environ, {"PYTHONPATH": str(checkout), "PYTHONHOME": str(checkout)}
            ):
                failures = smoke_test(
                    wheel, VERSION, pip_args=("--no-deps", "--no-index")
                )

        self.assertEqual(failures, [])

    def test_imports_must_come_from_the_test_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = _write_checkout(directory)
            # Model an installed package that redirects submodules to a source tree.
            redirected = dict(PACKAGE_FILES)
            redirected["__init__.py"] = (
                f"__path__.insert(0, {str(checkout / 'pymedphys')!r})\n"
                "from ._version import __version__\n"
            )
            wheel = _write_wheel(directory, package_files=redirected)

            failures = smoke_test(wheel, VERSION, pip_args=("--no-deps", "--no-index"))

        self.assertTrue(
            any("outside" in f and str(checkout) in f for f in failures), failures
        )


FILES_URL = "https://files.pythonhosted.org/"
PYPI = PackageIndex(index_url="https://pypi.org/simple/", files_url=FILES_URL)
WHEEL_NAME = f"pymedphys-{VERSION}-py3-none-any.whl"
SDIST_NAME = f"pymedphys-{VERSION}.tar.gz"


def _report(filename, *, version=VERSION, url=None, sha256="ab" * 32):
    """A pip installation report, reduced to the fields the check reads."""
    return {
        "version": "1",
        "install": [
            {
                "download_info": {
                    "url": url or f"{FILES_URL}packages/aa/bb/{filename}",
                    "archive_info": {
                        "hash": f"sha256={sha256}",
                        "hashes": {"sha256": sha256},
                    },
                },
                "is_direct": False,
                "metadata": {"name": "numpy", "version": "2.0.0"},
            },
            {
                "download_info": {
                    "url": url or f"{FILES_URL}packages/cc/dd/{filename}",
                    "archive_info": {
                        "hash": f"sha256={sha256}",
                        "hashes": {"sha256": sha256},
                    },
                },
                "is_direct": False,
                "metadata": {"name": "pymedphys", "version": version},
            },
        ],
    }


class InstallReportTests(unittest.TestCase):
    """The archive pip installed must be the published file in the right format."""

    def test_the_published_wheel_and_sdist_pass(self):
        self.assertEqual(
            check_install_report(_report(WHEEL_NAME), "wheel", VERSION, PYPI), []
        )
        self.assertEqual(
            check_install_report(_report(SDIST_NAME), "sdist", VERSION, PYPI), []
        )

    def test_the_wrong_format_fails(self):
        failures = check_install_report(_report(SDIST_NAME), "wheel", VERSION, PYPI)

        self.assertTrue(any(SDIST_NAME in f for f in failures), failures)

    def test_a_file_from_another_index_fails(self):
        # An extra index configured for pip may serve the same version.
        url = f"https://mirror.example.org/packages/{WHEEL_NAME}"

        failures = check_install_report(
            _report(WHEEL_NAME, url=url), "wheel", VERSION, PYPI
        )

        self.assertTrue(any(url in f and FILES_URL in f for f in failures), failures)

    def test_a_different_version_fails(self):
        report = _report("pymedphys-1.1.0-py3-none-any.whl", version="1.1.0")

        failures = check_install_report(report, "wheel", VERSION, PYPI)

        self.assertTrue(any("1.1.0" in f for f in failures), failures)

    def test_a_report_without_pymedphys_fails(self):
        report = _report(WHEEL_NAME)
        del report["install"][1]

        failures = check_install_report(report, "wheel", VERSION, PYPI)

        self.assertTrue(any("no pymedphys" in f for f in failures), failures)

    def test_hashes_are_compared_with_local_files(self):
        local = {WHEEL_NAME: "ab" * 32}
        self.assertEqual(
            check_install_report(
                _report(WHEEL_NAME), "wheel", VERSION, PYPI, local_hashes=local
            ),
            [],
        )

        failures = check_install_report(
            _report(WHEEL_NAME, sha256="cd" * 32),
            "wheel",
            VERSION,
            PYPI,
            local_hashes=local,
        )
        self.assertTrue(any("SHA-256" in f for f in failures), failures)

    def test_a_file_missing_from_the_local_copies_fails(self):
        failures = check_install_report(
            _report(WHEEL_NAME), "wheel", VERSION, PYPI, local_hashes={}
        )

        self.assertTrue(any("no local copy" in f for f in failures), failures)


def _write_simple_index(root, files_dir, names):
    """Serve the named files from a PEP 503 index directory, as pip reads it."""
    project = Path(root, "simple", "pymedphys")
    project.mkdir(parents=True, exist_ok=True)
    links = []
    for name in names:
        path = Path(files_dir, name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        links.append(f'<a href="{path.as_uri()}#sha256={digest}">{name}</a>')
    (project / "index.html").write_text(
        "<!DOCTYPE html><html><body>" + "".join(links) + "</body></html>",
        encoding="utf-8",
    )
    return PackageIndex(
        index_url=Path(root, "simple").as_uri() + "/",
        files_url=Path(files_dir).as_uri() + "/",
    )


class PublishedTests(unittest.TestCase):
    """Install each format from a local index into its own fresh environment."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.built = self.root / "built"
        self.built.mkdir()
        self.served = self.root / "files"
        self.served.mkdir()
        self.reports = self.root / "reports"
        self.reports.mkdir()
        _write_sdist(self.built, buildable=True)
        _write_wheel(self.built)

    def _publish(self, *names):
        for name in names:
            shutil.copy2(self.built / name, self.served / name)
        return _write_simple_index(self.root, self.served, names)

    def test_both_formats_pass_once_they_appear_on_the_index(self):
        # The first attempt finds nothing, as just after an upload.
        index = self._publish()
        sleeps = []

        def publish_then_sleep(seconds):
            sleeps.append(seconds)
            self._publish(WHEEL_NAME, SDIST_NAME)

        failures = check_published(
            VERSION,
            index,
            report_dir=self.reports,
            compare_with=self.built,
            wait=60,
            sleep=publish_then_sleep,
        )

        self.assertEqual(failures, [])
        self.assertEqual(len(sleeps), 1)
        for kind in ("wheel", "sdist"):
            self.assertTrue((self.reports / f"{kind}-install.json").is_file())
            self.assertTrue((self.reports / f"{kind}-install.log").is_file())

    def test_the_wheel_check_does_not_fall_back_to_the_sdist(self):
        index = self._publish(SDIST_NAME)

        failures = check_published(VERSION, index, report_dir=self.reports)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("wheel", failures[0])


if __name__ == "__main__":
    unittest.main()
