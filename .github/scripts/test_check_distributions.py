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
import os
import tarfile
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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


LICENCE_EXPRESSION = "Apache-2.0 AND MIT"
LICENCE_FILES = ("LICENSE", "lib/pymedphys/_pinnacle/LICENSE-MIT")


def _metadata(
    version, licence_expression=LICENCE_EXPRESSION, licence_files=LICENCE_FILES
):
    lines = ["Metadata-Version: 2.4", "Name: pymedphys", f"Version: {version}"]
    if licence_expression is not None:
        lines.append(f"License-Expression: {licence_expression}")
    lines += [f"License-File: {name}" for name in licence_files]
    return "\n".join(lines) + "\n"


def _write_sdist(
    directory,
    version=VERSION,
    package_files=PACKAGE_FILES,
    *,
    omit=(),
    licence_expression=LICENCE_EXPRESSION,
    declared_licence_files=LICENCE_FILES,
):
    root = f"pymedphys-{version}"
    files = {
        "PKG-INFO": _metadata(version, licence_expression, declared_licence_files),
        "lib/pymedphys/_pinnacle/LICENSE-MIT": "",
        "pyproject.toml": "",
        "README.rst": "",
        "CHANGELOG.md": "",
        "CONTRIBUTING.md": "",
        "LICENSE": "",
    }
    files.update(
        {f"lib/pymedphys/{name}": text for name, text in package_files.items()}
    )

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


def _write_wheel(
    directory,
    version=VERSION,
    package_files=PACKAGE_FILES,
    *,
    licence_expression=LICENCE_EXPRESSION,
    licence_files=LICENCE_FILES,
    declared_licence_files=LICENCE_FILES,
):
    dist_info = f"pymedphys-{version}.dist-info"
    files = {f"pymedphys/{name}": text for name, text in package_files.items()}
    files[f"{dist_info}/METADATA"] = _metadata(
        version, licence_expression, declared_licence_files
    )
    files.update({f"{dist_info}/licenses/{name}": "" for name in licence_files})
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

    def test_metadata_without_a_licence_expression_fails(self):
        sdist = _write_sdist(self.directory, licence_expression=None)
        wheel = _write_wheel(self.directory, licence_expression=None)

        failures = self._failures(sdist, wheel)

        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(all("License-Expression" in f for f in failures), failures)

    def test_declared_licence_file_missing_from_the_wheel_fails(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory, licence_files=("LICENSE",))

        failures = self._failures(sdist, wheel)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("lib/pymedphys/_pinnacle/LICENSE-MIT", failures[0])

    def test_declared_licence_file_missing_from_the_sdist_fails(self):
        sdist = _write_sdist(
            self.directory, omit=("lib/pymedphys/_pinnacle/LICENSE-MIT",)
        )
        wheel = _write_wheel(self.directory)

        failures = self._failures(sdist, wheel)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("sdist", failures[0])
        self.assertIn("LICENSE-MIT", failures[0])

    def test_missing_licence_file_declarations_fail(self):
        for kinds in (("sdist",), ("wheel",), ("sdist", "wheel")):
            for declared in ((), LICENCE_FILES[:1], LICENCE_FILES[1:]):
                with self.subTest(kinds=kinds, declared=declared):
                    # Leave the files present to isolate metadata omissions.
                    sdist = _write_sdist(
                        self.directory,
                        declared_licence_files=(
                            declared if "sdist" in kinds else LICENCE_FILES
                        ),
                    )
                    wheel = _write_wheel(
                        self.directory,
                        declared_licence_files=(
                            declared if "wheel" in kinds else LICENCE_FILES
                        ),
                    )

                    failures = self._failures(sdist, wheel)

                    for kind in kinds:
                        self.assertTrue(
                            any(kind in f and "License-File" in f for f in failures),
                            failures,
                        )

    def test_wheel_without_licence_declarations_or_files_fails(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(
            self.directory, declared_licence_files=(), licence_files=()
        )

        failures = self._failures(sdist, wheel)

        self.assertTrue(
            any("wheel" in f and "License-File" in f for f in failures), failures
        )

    def test_both_archives_omitting_the_same_licence_fail(self):
        # Agreement between archives must not hide a coordinated omission.
        sdist = _write_sdist(
            self.directory,
            declared_licence_files=("LICENSE",),
            omit=("lib/pymedphys/_pinnacle/LICENSE-MIT",),
        )
        wheel = _write_wheel(
            self.directory,
            declared_licence_files=("LICENSE",),
            licence_files=("LICENSE",),
        )

        failures = self._failures(sdist, wheel)

        for kind in ("sdist", "wheel"):
            self.assertTrue(
                any(kind in f and "LICENSE-MIT" in f for f in failures), failures
            )

    def test_wrong_licence_expressions_fail(self):
        for sdist_expression, wheel_expression in (
            ("MIT", LICENCE_EXPRESSION),
            (LICENCE_EXPRESSION, "MIT"),
            ("MIT", "MIT"),
        ):
            with self.subTest(sdist=sdist_expression, wheel=wheel_expression):
                sdist = _write_sdist(
                    self.directory, licence_expression=sdist_expression
                )
                wheel = _write_wheel(
                    self.directory, licence_expression=wheel_expression
                )

                failures = self._failures(sdist, wheel)

                for kind, expression in (
                    ("sdist", sdist_expression),
                    ("wheel", wheel_expression),
                ):
                    if expression != LICENCE_EXPRESSION:
                        self.assertTrue(
                            any(
                                kind in f and "License-Expression" in f
                                for f in failures
                            ),
                            failures,
                        )

    def test_reordered_licence_file_declarations_pass(self):
        sdist = _write_sdist(self.directory)
        wheel = _write_wheel(self.directory, declared_licence_files=LICENCE_FILES[::-1])

        self.assertEqual(self._failures(sdist, wheel), [])


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


if __name__ == "__main__":
    unittest.main()
