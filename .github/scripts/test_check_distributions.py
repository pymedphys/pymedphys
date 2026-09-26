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
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from check_distributions import (
    PackageIndex,
    _published_url,
    _run,
    check_build,
    check_contents,
    check_install_report,
    check_published,
    find_distributions,
    main,
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


LICENCE_EXPRESSION = "Apache-2.0 AND MIT"
LICENCE_FILES = ("LICENSE", "lib/pymedphys/_pinnacle/LICENSE-MIT")


def _metadata(
    version,
    licence_expression=LICENCE_EXPRESSION,
    licence_files=LICENCE_FILES,
    *,
    project_name="pymedphys",
    requires=(),
):
    lines = ["Metadata-Version: 2.4", f"Name: {project_name}", f"Version: {version}"]
    lines += [f"Requires-Dist: {requirement}" for requirement in requires]
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
    buildable=False,
    requires=(),
    build_requires=(),
    build_backend=BUILD_BACKEND,
):
    root = f"pymedphys-{version}"
    files = {
        "PKG-INFO": _metadata(
            version, licence_expression, declared_licence_files, requires=requires
        ),
        "lib/pymedphys/_pinnacle/LICENSE-MIT": "",
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
        files["pyproject.toml"] = BUILDABLE_PYPROJECT.replace(
            "requires = []", f"requires = {json.dumps(list(build_requires))}"
        )
        files["backend.py"] = build_backend

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
    project_name="pymedphys",
    requires=(),
):
    dist_info = f"{project_name}-{version}.dist-info"
    files = {f"{project_name}/{name}": text for name, text in package_files.items()}
    files[f"{dist_info}/METADATA"] = _metadata(
        version,
        licence_expression,
        declared_licence_files,
        project_name=project_name,
        requires=requires,
    )
    files.update({f"{dist_info}/licenses/{name}": "" for name in licence_files})
    files[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    if project_name == "pymedphys":
        files[f"{dist_info}/entry_points.txt"] = (
            "[console_scripts]\npymedphys = pymedphys.__main__:main\n"
        )

    record = [_record_line(name, text.encode()) for name, text in files.items()]
    record.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = "\n".join(record) + "\n"

    path = Path(directory, f"{project_name}-{version}-py3-none-any.whl")
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


class CanonicalVersionTests(unittest.TestCase):
    """The build copies the version string into the metadata unchanged."""

    def test_canonical_versions_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_sdist(directory)
            _write_wheel(directory)

            failures = check_build(Path(directory), None, skip_install=True)

        self.assertEqual(failures, [])

    def test_a_non_canonical_version_fails_before_publishing(self):
        # Hatchling writes "1.2.0-dev0" to the metadata but names the files
        # with the canonical "1.2.0.dev0", so a matching tag would publish.
        with tempfile.TemporaryDirectory() as directory:
            sdist = _write_sdist(directory, version="1.2.0-dev0")
            wheel = _write_wheel(directory, version="1.2.0-dev0")
            sdist.rename(Path(directory, SDIST_NAME))
            wheel.rename(Path(directory, WHEEL_NAME))

            failures = check_build(Path(directory), "v1.2.0-dev0", skip_install=True)

        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(all("canonical" in f for f in failures), failures)


class ArgumentTests(unittest.TestCase):
    """Options that do not apply to the chosen mode are errors, not ignored."""

    def _exits(self, argv):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(argv)
        return raised.exception.code

    def test_a_mode_is_required(self):
        self.assertEqual(self._exits([]), 2)

    def test_build_mode_rejects_published_options(self):
        for option in (
            ["--compare-with", "x"],
            ["--index", "testpypi"],
            ["--report-dir", "x"],
            ["--wait", "5"],
        ):
            with self.subTest(option=option):
                self.assertEqual(self._exits(["dist", *option]), 2)

    def test_published_mode_rejects_build_options(self):
        for option in (["dist"], ["--expected-version", "1"], ["--skip-install"]):
            with self.subTest(option=option):
                self.assertEqual(self._exits(["--published", "1", *option]), 2)


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


class SubprocessEnvironmentTests(unittest.TestCase):
    def test_explicit_network_settings_reach_the_child_process(self):
        settings = {
            "PIP_CERT": "/explicit/ca.pem",
            "PIP_CLIENT_CERT": "/explicit/client.pem",
            "PIP_PROXY": "http://proxy.example.invalid:8080",
            "PIP_TIMEOUT": "120",
            "PIP_DEFAULT_TIMEOUT": "120",
            "PIP_RETRIES": "8",
            "PIP_RESUME_RETRIES": "8",
            "HTTPS_PROXY": "http://proxy.example.invalid:8080",
            "SSL_CERT_FILE": "/explicit/ca.pem",
            "REQUESTS_CA_BUNDLE": "/explicit/ca.pem",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.dict(os.environ, settings),
        ):
            result = _run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import json, os; print(json.dumps(dict(os.environ)))",
                ],
                cwd=Path(directory),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        child_environment = json.loads(result.stdout)
        for name, value in settings.items():
            self.assertEqual(child_environment[name], value)


FILES_URL = "https://files.pythonhosted.org/"
PYPI = PackageIndex(
    project_url="https://pypi.org/simple/pymedphys/", files_url=FILES_URL
)
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


def _write_simple_index(root, files_dir, names, project_name="pymedphys"):
    """Provide the Simple API in JSON for discovery and HTML for pip."""
    project = Path(root, "simple", project_name)
    project.mkdir(parents=True, exist_ok=True)
    links = []
    files = []
    for name in names:
        path = Path(files_dir, name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        links.append(f'<a href="{path.as_uri()}#sha256={digest}">{name}</a>')
        files.append(
            {"filename": name, "url": path.as_uri(), "hashes": {"sha256": digest}}
        )
    (project / "index.html").write_text(
        "<!DOCTYPE html><html><body>" + "".join(links) + "</body></html>",
        encoding="utf-8",
    )
    metadata = project / "index.json"
    metadata.write_text(
        json.dumps({"meta": {"api-version": "1.0"}, "files": files}), encoding="utf-8"
    )
    return PackageIndex(
        project_url=metadata.as_uri(),
        files_url=Path(files_dir).as_uri() + "/",
        dependency_index_url=Path(root, "simple").as_uri() + "/",
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

    def _other_index(self):
        root = self.root / "other-index"
        files = root / "files"
        files.mkdir(parents=True)
        wrong = dict(PACKAGE_FILES, **{"_version.py": '__version__ = "0.0.0"\n'})
        _write_wheel(files, package_files=wrong)
        _write_sdist(files, package_files=wrong, buildable=True)
        return _write_simple_index(root, files, (WHEEL_NAME, SDIST_NAME))

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

    def test_the_sdist_check_does_not_fall_back_to_the_wheel(self):
        index = self._publish(WHEEL_NAME)

        failures = check_published(VERSION, index, report_dir=self.reports)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("sdist", failures[0])

    def test_other_indexes_cannot_substitute_the_same_version(self):
        other = self._other_index()
        index = dataclasses.replace(
            self._publish(WHEEL_NAME, SDIST_NAME),
            dependency_index_url=other.dependency_index_url,
        )
        with mock.patch.dict(
            os.environ, {"PIP_EXTRA_INDEX_URL": other.dependency_index_url}
        ):
            failures = check_published(
                VERSION, index, report_dir=self.reports, compare_with=self.built
            )

        self.assertEqual(failures, [])

    def test_waits_for_target_even_when_the_other_index_has_both_files(self):
        other = self._other_index()
        index = dataclasses.replace(
            self._publish(), dependency_index_url=other.dependency_index_url
        )
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

    def test_inherited_pip_targets_cannot_write_outside_the_environment(self):
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        target = self.root / "outside-the-environment"
        config = self.root / "pip.ini"
        config.write_text(f"[install]\ntarget = {target}\n", encoding="utf-8")

        for settings in (
            {"PIP_TARGET": str(target)},
            {"PIP_CONFIG_FILE": str(config)},
        ):
            with self.subTest(settings=settings):
                with mock.patch.dict(os.environ, settings):
                    failures = check_published(VERSION, index, report_dir=self.reports)

                self.assertEqual(failures, [])
                self.assertFalse(target.exists())

    def test_runtime_and_build_dependencies_ignore_inherited_pip_sources(self):
        # Fail the source build if pip picks the competing build dependency.
        backend = (
            "import release_dependency\n"
            "assert release_dependency.__version__ == '1.0.0'\n" + BUILD_BACKEND
        )
        _write_sdist(
            self.built,
            buildable=True,
            requires=("release-dependency",),
            build_requires=("release-dependency<2",),
            build_backend=backend,
        )
        _write_wheel(self.built, requires=("release-dependency",))
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        other = self._other_index()
        for root, files, version in (
            (self.root, self.served, "1.9.0"),
            (self.root / "other-index", self.root / "other-index/files", "1.0.0"),
        ):
            wheel = _write_wheel(
                files,
                version=version,
                project_name="release_dependency",
                package_files={"__init__.py": f"__version__ = {version!r}\n"},
            )
            _write_simple_index(root, files, (wheel.name,), "release-dependency")
        index = dataclasses.replace(
            index, dependency_index_url=other.dependency_index_url
        )

        extra_index = (self.root / "simple").as_uri() + "/"
        find_links = self.served.as_uri()
        config = self.root / "pip.ini"
        config.write_text(
            f"[global]\nextra-index-url = {extra_index}\nfind-links = {find_links}\n",
            encoding="utf-8",
        )
        for settings in (
            {"PIP_EXTRA_INDEX_URL": extra_index, "PIP_FIND_LINKS": find_links},
            {"PIP_CONFIG_FILE": str(config)},
        ):
            with self.subTest(settings=settings):
                with mock.patch.dict(os.environ, settings):
                    failures = check_published(VERSION, index, report_dir=self.reports)

                self.assertEqual(failures, [])
                for kind in ("wheel", "sdist"):
                    report = json.loads(
                        (self.reports / f"{kind}-install.json").read_text()
                    )
                    dependency = next(
                        entry
                        for entry in report["install"]
                        if entry["metadata"]["name"].replace("_", "-")
                        == "release-dependency"
                    )
                    self.assertEqual(dependency["metadata"]["version"], "1.0.0")

    def test_a_transient_index_error_is_retried_within_the_wait(self):
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        real_urlopen = urllib.request.urlopen
        responses = iter(
            [urllib.error.HTTPError(index.project_url, 503, "Unavailable", {}, None)]
        )

        def flaky_urlopen(*args, **kwargs):
            error = next(responses, None)
            if error is not None:
                raise error
            return real_urlopen(*args, **kwargs)

        sleeps = []
        with mock.patch("urllib.request.urlopen", flaky_urlopen):
            url = _published_url(index, "wheel", VERSION, wait=60, sleep=sleeps.append)

        self.assertEqual(len(sleeps), 1)
        self.assertIn(WHEEL_NAME, url)

    def test_a_permanent_index_error_is_not_retried(self):
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        error = urllib.error.HTTPError(index.project_url, 403, "Forbidden", {}, None)

        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                _published_url(index, "wheel", VERSION, wait=60, sleep=self.fail)

    def test_rejects_an_index_link_to_another_host_before_installing(self):
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        wrong_host = dataclasses.replace(index, files_url="https://example.org/")

        with self.assertRaisesRegex(ValueError, "not served from"):
            _published_url(wrong_host, "wheel", VERSION, wait=0, sleep=lambda _: None)

    def test_a_file_differing_from_the_local_copy_is_not_installed(self):
        # With --compare-with, a mismatched archive (for example one kept by
        # skip-existing) is rejected before pip downloads or builds it.
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        self._other_index()

        failures = check_published(
            VERSION,
            index,
            report_dir=self.reports,
            compare_with=self.root / "other-index" / "files",
        )

        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(all("SHA-256" in f for f in failures), failures)
        for kind in ("wheel", "sdist"):
            self.assertFalse((self.reports / f"{kind}-install.json").exists())

    def test_downloaded_bytes_must_match_the_index_hash(self):
        index = self._publish(WHEEL_NAME, SDIST_NAME)
        metadata = self.root / "simple/pymedphys/index.json"
        listing = json.loads(metadata.read_text())
        listing["files"][0]["hashes"]["sha256"] = "ab" * 32
        metadata.write_text(json.dumps(listing))

        failures = check_published(VERSION, index, report_dir=self.reports)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("Installing the wheel", failures[0])
        self.assertIn(
            "DO NOT MATCH THE HASHES", (self.reports / "wheel-install.log").read_text()
        )


if __name__ == "__main__":
    unittest.main()
