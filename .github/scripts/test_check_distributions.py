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

"""Tests for the pre-publication distribution checks, on synthetic archives."""

import base64
import hashlib
import io
import tarfile
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

from check_distributions import (
    check_contents,
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


def _metadata(version):
    return f"Metadata-Version: 2.4\nName: pymedphys\nVersion: {version}\n"


def _write_sdist(directory, version=VERSION, package_files=PACKAGE_FILES):
    root = f"pymedphys-{version}"
    files = {
        "PKG-INFO": _metadata(version),
        "pyproject.toml": "",
        "README.rst": "",
        "LICENSE": "",
    }
    files.update(
        {f"lib/pymedphys/{name}": text for name, text in package_files.items()}
    )

    path = Path(directory, f"{root}.tar.gz")
    with tarfile.open(path, "w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    return path


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


if __name__ == "__main__":
    unittest.main()
