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

"""Exercise safe skips, conservative fallbacks and real merge-tree diffs."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from check_workflow_status import check_jobs
from select_checks import OUTPUTS, changed_paths, select_checks


class SelectionTests(unittest.TestCase):
    def test_documentation_does_not_run_python(self):
        for path in (
            "README.rst",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "lib/pymedphys/docs/contrib/info/workflows.md",
            "docs/users/example.ipynb",
            "lib/pymedphys/docs/image.png",
        ):
            with self.subTest(path=path):
                selected = select_checks([path])
                self.assertTrue(selected.pop("run-docs"))
                self.assertFalse(any(selected.values()))

    def test_package_code_runs_python_and_generated_docs(self):
        selected = select_checks(["lib/pymedphys/_gamma/implementation.py"])
        self.assertTrue(selected["run-python"])
        self.assertTrue(selected["run-docs"])
        self.assertTrue(selected["run-python-security"])
        self.assertTrue(selected["run-dependency-audit"])
        self.assertTrue(selected["run-workflow-audit"])

    def test_tests_do_not_change_rendered_docs(self):
        selected = select_checks(["lib/pymedphys/tests/dicom/test_dose.py"])
        self.assertTrue(selected["run-python"])
        self.assertFalse(selected["run-docs"])

    def test_executable_docs_are_not_exempt(self):
        for path in (
            "lib/pymedphys/docs/conftest.py",
            "docs/helper.py",
            "lib/pymedphys/docs/_config.yml",
            "docs/new-format.xyz",
        ):
            with self.subTest(path=path):
                self.assertTrue(select_checks([path])["run-python"])

    def test_unknown_dependency_fixture_and_ci_inputs_select_everything(self):
        for path in (
            "pyproject.toml",
            "uv.lock",
            "requirements-docs.txt",
            "new-directory/input",
            ".github/workflows/release.yml",
            ".github/scripts/select_checks.py",
            ".pre-commit-config.yaml",
            "lib/pymedphys/tests/fixture.csv",
            "docs",
            ".readthedocs.yml",
            "claude_created_workflows_preview/release.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(all(select_checks([path]).values()))

    def test_database_and_shared_code_select_database_tests(self):
        for path in (
            "lib/pymedphys/_mosaiq/api.py",
            "lib/pymedphys/tests/mosaiq/test_db.py",
            "lib/pymedphys/conftest.py",
            "lib/pymedphys/_imports/__init__.py",
            "lib/pymedphys/_data/download.py",
            "lib/pymedphys/_base/delivery.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(select_checks([path])["run-database"])

    def test_mixed_changes_cannot_be_hidden_by_docs(self):
        selected = select_checks(["README.rst", "lib/pymedphys/_gamma/core.py"])
        self.assertTrue(selected["run-python"])
        self.assertTrue(selected["run-docs"])

    def test_labels_only_add_coverage(self):
        self.assertTrue(
            all(select_checks(["README.rst"], labels=["full-test"]).values())
        )
        self.assertTrue(
            select_checks(["README.rst"], labels=["database"])["run-database"]
        )
        self.assertFalse(select_checks(["README.rst"], labels=[])["run-database"])

    def test_non_pr_and_unverifiable_diffs_keep_full_coverage(self):
        for event in ("release", "schedule", "workflow_dispatch", "merge_group"):
            with self.subTest(event=event):
                self.assertTrue(all(select_checks([], event_name=event).values()))
        self.assertTrue(all(select_checks(None).values()))
        pushed = select_checks(["README.rst"], event_name="push")
        self.assertFalse(pushed.pop("run-docs"))
        self.assertTrue(all(pushed.values()))

    def test_every_selection_has_explicit_booleans(self):
        for paths in (None, [], ["README.rst"], ["new-file"]):
            result = select_checks(paths)
            self.assertEqual(set(result), set(OUTPUTS))
            self.assertTrue(all(isinstance(value, bool) for value in result.values()))

    def test_selected_jobs_cannot_be_skipped_at_the_merge_gate(self):
        conditional = {
            "unit-tests": "run-python",
            "lint": "run-python",
            "type-check": "run-python",
            "script-tests": "run-scripts",
        }
        for paths in (["README.rst"], ["uv.lock"], None):
            selection = {
                key: str(value).lower() for key, value in select_checks(paths).items()
            }
            needs = {
                "changes": {"result": "success", "outputs": selection},
                **{job: {"result": "skipped"} for job in conditional},
            }
            self.assertEqual(
                not check_jobs(needs, conditional), paths == ["README.rst"]
            )
            del needs["changes"]["outputs"]["run-python"]
            self.assertTrue(check_jobs(needs, conditional))


class DiffTests(unittest.TestCase):
    event = {"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}

    def test_missing_or_mismatched_merge_metadata_falls_back(self):
        for parents in (b"", b"head", b"different head", b"base head extra"):
            self.assertIsNone(changed_paths(self.event, git=Mock(return_value=parents)))
        self.assertIsNone(changed_paths({}, git=Mock()))
        self.assertIsNone(changed_paths(self.event, git=Mock(side_effect=OSError())))

    def test_diff_errors_and_invalid_encoding_fall_back(self):
        for error in (subprocess.CalledProcessError(1, "git"), b"bad-\xff\0"):
            git = Mock(side_effect=[b"base head", error])
            self.assertIsNone(changed_paths(self.event, git=git))

    def test_no_file_count_limit_and_literal_filenames(self):
        paths = [f"docs/page-{number}.md" for number in range(4000)]
        paths += [
            "docs/line\nbreak.md",
            "docs/$(command).md",
            "lib/pymedphys/deleted.py",
        ]
        git = Mock(side_effect=[b"base head", ("\0".join(paths) + "\0").encode()])
        result = changed_paths(self.event, git=git)
        self.assertEqual(result, paths)
        self.assertTrue(select_checks(result)["run-python"])

    def test_real_merge_keeps_deletions_and_both_sides_of_renames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=root, stderr=subprocess.DEVNULL
                )

            git("init", "-b", "main")
            git("config", "user.name", "CI policy test")
            git("config", "user.email", "ci@example.invalid")
            (root / "code.py").write_text("pass\n")
            (root / "deleted.py").write_text("pass\n")
            git("add", ".")
            git("commit", "-m", "base")
            base = git("rev-parse", "HEAD").decode().strip()
            git("switch", "-c", "change")
            (root / "code.py").rename(root / "README.rst")
            (root / "deleted.py").unlink()
            git("add", "-A")
            git("commit", "-m", "rename and delete")
            head = git("rev-parse", "HEAD").decode().strip()
            git("switch", "main")
            git("merge", "--no-ff", "change", "-m", "test merge")
            event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
            paths = changed_paths(event, git=lambda args: git(*args[1:]))
            self.assertEqual(set(paths), {"code.py", "README.rst", "deleted.py"})
            self.assertTrue(all(select_checks(paths).values()))
            # Exercise the exact shallow history used by Actions, without a
            # network or an API response that could truncate the changed files.
            with tempfile.TemporaryDirectory() as checkout:
                git("clone", "--depth=2", "--no-local", root.as_uri(), checkout)

                def shallow_git(args):
                    return subprocess.check_output(args, cwd=checkout)

                self.assertEqual(
                    shallow_git(
                        ["git", "rev-parse", "--is-shallow-repository"]
                    ).strip(),
                    b"true",
                )
                self.assertEqual(changed_paths(event, git=shallow_git), paths)


if __name__ == "__main__":
    unittest.main()
