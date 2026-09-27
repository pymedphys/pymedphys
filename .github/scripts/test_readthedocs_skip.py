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

"""Read the Docs cancels only pull-request builds that cannot change the site."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / ".github" / "scripts" / "readthedocs_skip.sh"
CANCEL = 183

# Paths the skip treats as unable to change the documentation build.
UNAFFECTED = (
    ".github/workflows/ci.yml",
    ".github/scripts/select_checks.py",
    "lib/pymedphys/tests/gamma/test_gamma.py",
    "AGENTS.md",
    "CLAUDE.md",
    "SECURITY.md",
    ".pre-commit-config.yaml",
    "claude_created_workflows_preview/ci.yml",
)
# Inputs of the documentation build, and a path the skip does not recognise.
AFFECTED = (
    "lib/pymedphys/_gamma/implementation.py",
    "lib/pymedphys/docs/index.rst",
    "README.rst",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "uv.lock",
    ".readthedocs.yml",
    "unknown/file.txt",
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipIf(
    sys.platform == "win32" or shutil.which("bash") is None,
    "Read the Docs runs the script with bash on Linux",
)
class ReadTheDocsSkipTests(unittest.TestCase):
    def setUp(self):
        self.repository = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repository, ignore_errors=True)
        _git(self.repository, "init", "-q")
        _git(self.repository, "config", "user.email", "test@example.com")
        _git(self.repository, "config", "user.name", "Test")
        for path in UNAFFECTED + AFFECTED:
            self._write(path, "main\n")
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-q", "-m", "main")
        # Read the Docs clones the default branch before checking out the PR.
        _git(self.repository, "update-ref", "refs/remotes/origin/main", "HEAD")

    def _write(self, path: str, text: str) -> None:
        target = self.repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _commit_change(self, *paths: str) -> None:
        for path in paths:
            self._write(path, "pull request\n")
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-q", "-m", "pull request")

    def _run(self, version_type: str = "external") -> int:
        environment = dict(os.environ, READTHEDOCS_VERSION_TYPE=version_type)
        return subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=self.repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        ).returncode

    def test_pull_request_touching_only_unaffected_paths_is_cancelled(self):
        self._commit_change(*UNAFFECTED)
        self.assertEqual(self._run(), CANCEL)

    def test_pull_request_touching_any_other_path_builds(self):
        for path in AFFECTED:
            with self.subTest(path=path):
                _git(self.repository, "reset", "-q", "--hard", "origin/main")
                self._commit_change(UNAFFECTED[0], path)
                self.assertEqual(self._run(), 0)

    def test_deleting_a_documentation_input_builds(self):
        (self.repository / "README.rst").unlink()
        _git(self.repository, "commit", "-q", "-am", "delete")
        self.assertEqual(self._run(), 0)

    def test_branch_and_tag_builds_are_never_cancelled(self):
        self._commit_change(*UNAFFECTED)
        for version_type in ("branch", "tag", ""):
            with self.subTest(version_type=version_type):
                self.assertEqual(self._run(version_type), 0)

    def test_a_failed_comparison_builds(self):
        self._commit_change(*UNAFFECTED)
        _git(self.repository, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self._run(), 0)


class ConfigurationTests(unittest.TestCase):
    def test_read_the_docs_runs_the_script_after_checkout(self):
        config = (REPOSITORY / ".readthedocs.yml").read_text(encoding="utf-8")
        self.assertIn(
            "    post_checkout:\n      - bash .github/scripts/readthedocs_skip.sh\n",
            config,
        )


if __name__ == "__main__":
    unittest.main()
