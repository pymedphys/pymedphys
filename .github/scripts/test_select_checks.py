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

import ast
import os
import re
import subprocess
import tempfile
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from unittest.mock import Mock

from check_workflow_status import check_jobs
from select_checks import (
    COST_GATED,
    DOCTEST_FILES,
    OUTPUTS,
    PATH_SELECTABLE,
    SLOW_TEST_FILES,
    STANDARD,
    ChangedPath,
    changed_paths,
    explain_checks,
    parse_raw_diff,
    render_summary,
    select_checks,
)

SHA = "1" * 40
# Keep the developer's global and system git configuration, such as commit
# signing or hooks, out of the throwaway repositories.
GIT_ENVIRONMENT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "CI policy test",
    "GIT_AUTHOR_EMAIL": "ci@example.invalid",
    "GIT_COMMITTER_NAME": "CI policy test",
    "GIT_COMMITTER_EMAIL": "ci@example.invalid",
}


def raw_record(
    name: str, old: str = "100644", new: str = "100644", status: str = "M"
) -> bytes:
    return f":{old} {new} {SHA} {SHA} {status}\0{name}\0".encode()


def selected(result: Mapping[str, bool]) -> set[str]:
    return {output for output, enabled in result.items() if enabled}


def git_in(
    root: str | Path,
    *args: str,
    stdin: bytes | None = None,
    index: Path | None = None,
) -> bytes:
    environment = GIT_ENVIRONMENT
    if index is not None:
        environment = {**environment, "GIT_INDEX_FILE": str(index)}
    return subprocess.check_output(
        ["git", *args],
        cwd=root,
        input=stdin,
        env=environment,
        stderr=subprocess.DEVNULL,
    )


REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE = "lib/pymedphys"
# A doctest example starts on a line holding only indentation before ">>>".
DOCTEST_PROMPT = re.compile(r"^[ \t]*>>>", re.MULTILINE)


def applies_slow_marker(tree: ast.AST) -> bool:
    """Whether a module applies pytest's slow marker in any static form."""
    marks = {"mark"}
    for node in ast.walk(tree):
        # Aliases such as `from pytest import mark as m` and `m = pytest.mark`.
        if isinstance(node, ast.ImportFrom):
            marks.update(
                alias.asname
                for alias in node.names
                if alias.name == "mark" and alias.asname is not None
            )
        elif (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
        ):
            marks.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "slow":
            value = node.value
            if (isinstance(value, ast.Attribute) and value.attr == "mark") or (
                isinstance(value, ast.Name) and value.id in marks
            ):
                return True
        # getattr(pytest.mark, "slow") and item.add_marker("slow").
        if isinstance(node, ast.Call) and any(
            isinstance(arg, ast.Constant) and arg.value == "slow" for arg in node.args
        ):
            function = node.func
            if (isinstance(function, ast.Name) and function.id == "getattr") or (
                isinstance(function, ast.Attribute) and function.attr == "add_marker"
            ):
                return True
    return False


def _assigned_name(target: ast.expr) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def has_doctest_examples(tree: ast.AST) -> bool:
    """Whether a module holds examples where doctest looks for them."""
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            texts = [ast.get_docstring(node, clean=False) or ""]
        elif isinstance(node, ast.Assign):
            names = {_assigned_name(target) for target in node.targets}
            # Doctest reads every entry of a module's __test__ mapping.
            if "__test__" in names:
                return True
            if "__doc__" not in names:
                continue
            texts = [
                child.value
                for child in ast.walk(node.value)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            ]
        else:
            continue
        if any(DOCTEST_PROMPT.search(text) for text in texts):
            return True
    return False


def scan_package(predicate: Callable[[ast.AST], bool]) -> set[str]:
    """Return the package modules, tracked or not yet added, matching a predicate."""
    # -t tags each path; "S" marks one that a sparse checkout left out.
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "-t", "--cached", "--others", "--exclude-standard"]
        + ["--", PACKAGE],
        cwd=REPOSITORY,
    )
    found: set[str] = set()
    for entry in filter(None, listed.decode("utf-8").split("\0")):
        tag, name = entry.split(" ", 1)
        if tag == "S":
            raise RuntimeError(f"The package scan needs all of {PACKAGE} checked out.")
        source = REPOSITORY / name
        # Skip files deleted from the working tree but not yet from the index.
        if name.endswith(".py") and source.is_file():
            tree = ast.parse(source.read_bytes(), filename=name)
            if predicate(tree):
                found.add(name)
    return found


class SelectionTests(unittest.TestCase):
    def test_documentation_does_not_run_python(self):
        for path in (
            "README.rst",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "lib/pymedphys/docs/contrib/info/workflows.md",
            "lib/pymedphys/docs/users/example.ipynb",
            "lib/pymedphys/docs/image.png",
        ):
            with self.subTest(path=path):
                self.assertEqual(selected(select_checks([path])), {"run-docs"})

    def test_package_code_runs_python_and_generated_docs(self):
        result = select_checks(["lib/pymedphys/_gamma/implementation.py"])
        self.assertEqual(
            selected(result),
            {
                "run-python",
                "run-docs",
                "run-python-security",
                "run-dependency-audit",
                "run-workflow-audit",
            },
        )

    def test_tests_do_not_change_rendered_docs(self):
        result = select_checks(["lib/pymedphys/tests/dicom/test_dose.py"])
        self.assertTrue(result["run-python"])
        self.assertFalse(result["run-docs"])

    def test_executable_docs_are_not_exempt(self):
        for path in (
            "lib/pymedphys/docs/conftest.py",
            "lib/pymedphys/docs/helper.py",
            "lib/pymedphys/docs/_config.yml",
            "lib/pymedphys/docs/new-format.xyz",
            "lib/pymedphys/docs/IMAGE.PNG",
            "lib/pymedphys/docs/.gitignore",
        ):
            with self.subTest(path=path):
                self.assertTrue(select_checks([path])["run-python"])

    def test_the_root_docs_symlink_is_not_documentation(self):
        # Git reports the repository-root link itself, never paths beneath it.
        link = ChangedPath("docs", regular=False)
        self.assertEqual(selected(select_checks([link])), set(PATH_SELECTABLE))
        self.assertTrue(select_checks(["docs/page.md"])["run-python"])

    def test_unknown_inputs_select_every_standard_check(self):
        for path in (
            "new-directory/input",
            ".github/workflows/release.yml",
            ".github/workflows/claude.yml",
            ".pre-commit-config.yaml",
            "other-directory/fixture.csv",
            "docs/page.md",
            ".readthedocs.yml",
            "claude_created_workflows_preview/release.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(selected(select_checks([path])), set(STANDARD))

    def test_costly_checks_run_for_the_inputs_only_they_validate(self):
        both = {"run-integration", "run-database"}
        for path, expected in (
            ("pyproject.toml", both),
            ("uv.lock", both),
            ("requirements.txt", both),
            ("requirements-docs.txt", both),
            ("pyproject.hash", both),
            ("lib/pymedphys/dependency-extra.txt", both),
            ("lib/pymedphys/_version.py", both),
            (".github/workflows/ci.yml", both),
            (".github/actions/setup-project/action.yml", both),
            (".github/workflows/integration-tests.yml", {"run-integration"}),
            (".github/scripts/check_distributions.py", {"run-integration"}),
            (".github/scripts/select_checks.py", {"run-integration"}),
            ("examples/stackoverflow/gamma.py", {"run-integration"}),
            (".github/workflows/mosaiq-db-tests.yml", {"run-database"}),
            ("docker/mosaiq/docker-compose.yml", {"run-database"}),
            ("lib/pymedphys/_mosaiq/mock/data.csv", {"run-database"}),
            ("lib/pymedphys/_data/hashes.json", both),
            ("lib/pymedphys/_metersetmap/metersetmap.py", {"run-integration"}),
            ("lib/pymedphys/_mosaiq/api.py", both),
            ("lib/pymedphys/_gamma/implementation/shell.py", set()),
            (".github/workflows/claude.yml", set()),
            ("lib/pymedphys/tests/fixture.csv", {"run-integration"}),
            ("lib/pymedphys/docs/users/howto/mosaiq.md", set()),
        ):
            with self.subTest(path=path):
                result = selected(select_checks([path]))
                self.assertEqual(result & set(COST_GATED), expected)

    def test_packaging_filters_select_distribution_checks(self):
        for path in (
            ".gitignore",
            ".gitattributes",
            ".hgignore",
            "lib/pymedphys/.gitignore",
            "lib/pymedphys/docs/.gitignore",
        ):
            with self.subTest(path=path):
                result = select_checks([path])
                self.assertTrue(result["run-integration"])
                self.assertFalse(result["run-full-matrix"])

    def test_slow_modules_run_without_enabling_every_test_change(self):
        for path in (
            "lib/pymedphys/tests/metersetmap/test_metersetmap_regression.py",
            "lib/pymedphys/tests/pinnacle/test_pinnacle_cli.py",
        ):
            with self.subTest(path=path):
                result = select_checks([path])
                self.assertTrue(result["run-integration"])
                self.assertFalse(result["run-full-matrix"])
        self.assertFalse(
            select_checks(["lib/pymedphys/tests/dicom/test_dose.py"])["run-integration"]
        )

    def test_shared_slow_inputs_select_integration_tests(self):
        for path in (
            "lib/pymedphys/_data/urls.json",
            "lib/pymedphys/_data/hashes.json",
            "lib/pymedphys/_data/download.py",
            "lib/pymedphys/_utilities/test.py",
            "lib/pymedphys/_imports/__init__.py",
            "lib/pymedphys/_base/delivery.py",
            "lib/pymedphys/conftest.py",
            "lib/pymedphys/tests/pinnacle/conftest.py",
            "lib/pymedphys/tests/fixture.csv",
        ):
            with self.subTest(path=path):
                self.assertTrue(select_checks([path])["run-integration"])

    def test_integration_input_skips_fail_the_merge_gate(self):
        for path in (
            ".gitignore",
            "lib/pymedphys/_data/urls.json",
            "lib/pymedphys/tests/metersetmap/test_metersetmap_regression.py",
        ):
            with self.subTest(path=path):
                outputs = {
                    key: str(value).lower()
                    for key, value in select_checks([path]).items()
                }
                needs = {
                    "changes": {"result": "success", "outputs": outputs},
                    "integration-tests": {"result": "skipped"},
                }
                conditional = {"integration-tests": "run-integration"}
                self.assertTrue(check_jobs(needs, conditional))
                needs["integration-tests"]["result"] = "success"
                self.assertEqual(check_jobs(needs, conditional), [])

    def test_database_and_shared_code_select_database_tests(self):
        for path in (
            "lib/pymedphys/_mosaiq/api.py",
            "lib/pymedphys/tests/mosaiq/test_db.py",
            "lib/pymedphys/conftest.py",
            "lib/pymedphys/_imports/__init__.py",
            "lib/pymedphys/_data/download.py",
            "lib/pymedphys/_utilities/constants.py",
            "lib/pymedphys/_base/delivery.py",
            "lib/pymedphys/mosaiq.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(select_checks([path])["run-database"])
        self.assertFalse(
            select_checks(["lib/pymedphys/_gamma/core.py"])["run-database"]
        )

    def test_mixed_changes_cannot_be_hidden_by_docs(self):
        result = select_checks(["README.rst", "lib/pymedphys/_gamma/core.py"])
        self.assertTrue(result["run-python"])
        self.assertTrue(result["run-docs"])

    def test_labels_only_add_coverage(self):
        self.assertTrue(
            all(select_checks(["README.rst"], labels=["full-test"]).values())
        )
        self.assertTrue(
            select_checks(["README.rst"], labels=["database"])["run-database"]
        )
        self.assertFalse(select_checks(["README.rst"], labels=[])["run-database"])

    def test_labels_match_case_insensitively_like_github_contains(self):
        self.assertTrue(
            all(select_checks(["README.rst"], labels=["Full-Test"]).values())
        )
        self.assertTrue(
            select_checks(["README.rst"], labels=["DATABASE"])["run-database"]
        )

    def test_only_main_and_full_test_widen_the_unit_test_matrix(self):
        self.assertTrue(select_checks([], event_name="push")["run-full-matrix"])
        self.assertTrue(select_checks([], labels=["full-test"])["run-full-matrix"])
        for paths in (None, [], ["uv.lock"], ["lib/pymedphys/_gamma/core.py"]):
            with self.subTest(paths=paths):
                self.assertFalse(select_checks(paths)["run-full-matrix"])

    def test_non_pr_and_unverifiable_diffs_keep_full_coverage(self):
        for event in ("release", "schedule", "workflow_dispatch", "merge_group"):
            with self.subTest(event=event):
                self.assertTrue(all(select_checks([], event_name=event).values()))
        self.assertEqual(selected(select_checks(None)), set(PATH_SELECTABLE))
        pushed = select_checks(["README.rst"], event_name="push")
        self.assertFalse(pushed.pop("run-docs"))
        self.assertTrue(all(pushed.values()))

    def test_every_selection_has_explicit_booleans(self):
        for paths in (None, [], ["README.rst"], ["new-file"]):
            result = select_checks(paths)
            self.assertEqual(tuple(result), OUTPUTS)
            self.assertTrue(all(isinstance(value, bool) for value in result.values()))

    def test_symlinks_and_submodules_select_every_path_check(self):
        for regular in (True, False):
            with self.subTest(regular=regular):
                result = select_checks([ChangedPath("README.rst", regular)])
                expected = {"run-docs"} if regular else set(PATH_SELECTABLE)
                self.assertEqual(selected(result), expected)

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


class RepositoryScanTests(unittest.TestCase):
    """Keep the selector's module lists equal to what the package contains."""

    def assert_list_matches_scan(
        self,
        name: str,
        listed: frozenset[str],
        predicate: Callable[[ast.AST], bool],
        description: str,
    ) -> None:
        found = scan_package(predicate)
        missing = sorted(found - listed)
        stale = sorted(listed - found)
        if missing or stale:
            self.fail(
                "\n".join(
                    [
                        f"{name} in .github/scripts/select_checks.py must list "
                        f"exactly the package modules that {description}, so "
                        "that a pull request changing one runs the integration "
                        "tests.",
                        *(f"Add: {path}" for path in missing),
                        *(f"Remove: {path}" for path in stale),
                    ]
                )
            )

    def test_slow_test_list_matches_the_package(self):
        self.assert_list_matches_scan(
            "SLOW_TEST_FILES",
            SLOW_TEST_FILES,
            applies_slow_marker,
            "apply pytest's slow marker",
        )

    def test_doctest_list_matches_the_package(self):
        self.assert_list_matches_scan(
            "DOCTEST_FILES", DOCTEST_FILES, has_doctest_examples, "hold doctests"
        )

    def test_listed_modules_select_integration_tests(self):
        for path in sorted(SLOW_TEST_FILES | DOCTEST_FILES):
            with self.subTest(path=path):
                result = select_checks([path])
                self.assertTrue(result["run-integration"])
                self.assertFalse(result["run-full-matrix"])

    def test_static_slow_markers_are_detected(self):
        for source in (
            "import pytest\n@pytest.mark.slow\ndef test(): pass",
            "import pytest as pt\n@pt.mark.slow\ndef test(): pass",
            "from pytest import mark\n@mark.slow\ndef test(): pass",
            "from pytest import mark as m\n@m.slow\ndef test(): pass",
            "import pytest\nm = pytest.mark\n@m.slow\ndef test(): pass",
            "import pytest\npytestmark = [pytest.mark.slow]",
            "import pytest\nCASES = [pytest.param(1, marks=pytest.mark.slow)]",
            "import pytest\n@getattr(pytest.mark, 'slow')\ndef test(): pass",
            "def pytest_collection_modifyitems(items):\n"
            "    items[0].add_marker('slow')",
        ):
            with self.subTest(source=source):
                self.assertTrue(applies_slow_marker(ast.parse(source)))
        for source in (
            "import pytest\n@pytest.mark.slowest\ndef test(): pass",
            "def test(options): assert options.slow",
            "SOURCE = '@pytest.mark.slow\\ndef test(): pass'",
            "MARKERS = {'slow': '--slow'}",
        ):
            with self.subTest(source=source):
                self.assertFalse(applies_slow_marker(ast.parse(source)))

    def test_doctests_are_detected_where_doctest_looks(self):
        for source in (
            '""">>> 1\n1\n"""',
            'def f():\n    """Return one.\n\n    >>> f()\n    1\n    """',
            'class C:\n    def f(self):\n        """\n        >>> C().f()\n        """',
            'async def f():\n    """\n    >>> f\n    """',
            'f.__doc__ = """\n>>> 1\n"""',
            "__test__ = build_examples()",
        ):
            with self.subTest(source=source):
                self.assertTrue(has_doctest_examples(ast.parse(source)))
        for source in (
            'SAMPLE = """\n>>> 1 + 1\n2\n"""',
            "# >>> 1",
            'def f():\n    """Shift with a >>> b."""',
            "__doc__ = property(get_doc)",
        ):
            with self.subTest(source=source):
                self.assertFalse(has_doctest_examples(ast.parse(source)))


class SummaryTests(unittest.TestCase):
    def test_reasons_name_the_first_path_or_policy(self):
        reasons = explain_checks(
            ["README.rst", "lib/pymedphys/_gamma/core.py", "uv.lock"],
            labels=["database"],
        )
        self.assertEqual(reasons["run-docs"], ("documentation", "README.rst"))
        self.assertEqual(
            reasons["run-python"], ("package Python", "lib/pymedphys/_gamma/core.py")
        )
        self.assertEqual(reasons["run-scripts"], ("unclassified input", "uv.lock"))
        self.assertEqual(reasons["run-integration"], ("integration input", "uv.lock"))
        self.assertEqual(reasons["run-database"], ("database label", None))
        self.assertIsNone(reasons["run-full-matrix"])

    def test_summary_names_the_path_that_forced_the_fallback(self):
        changes = [
            ChangedPath("README.rst"),
            ChangedPath("pyproject.toml"),
            ChangedPath("uv.lock"),
        ]
        summary = render_summary(explain_checks(changes), changes)
        self.assertIn(
            "Fallback: ` pyproject.toml ` is not a recognised documentation or "
            "package Python input, so it selects every standard check.",
            summary,
        )
        self.assertIn("1 more changed path is also unclassified.", summary)
        self.assertIn("| run-docs | yes | documentation ` README.rst ` |", summary)

    def test_summary_explains_links_and_unverified_diffs(self):
        changes = [
            ChangedPath("uv.lock"),
            ChangedPath("lib/pymedphys/docs/page.md", regular=False),
        ]
        summary = render_summary(explain_checks(changes), changes)
        # The link selects the most, so it is named even though it came second.
        self.assertIn(
            "Fallback: ` lib/pymedphys/docs/page.md ` is a symlink or submodule, "
            "so it selects every check that a changed path can select.",
            summary,
        )
        summary = render_summary(explain_checks(None), None)
        self.assertIn("could not be verified", summary)
        self.assertNotIn("Fallback", summary)

    def test_label_selections_have_no_fallback_note(self):
        changes = [ChangedPath("uv.lock")]
        summary = render_summary(explain_checks(changes, labels=["full-test"]), changes)
        self.assertIn("full-test label", summary)
        self.assertNotIn("Fallback", summary)

    def test_hostile_paths_cannot_break_or_disguise_the_summary(self):
        name = "a|b`c\nd‮exe.md"
        changes = [ChangedPath(name)]
        summary = render_summary(explain_checks(changes), changes)
        self.assertNotIn("‮", summary)
        self.assertNotIn(name, summary)
        self.assertIn("a\\|b`c\\nd\\u202eexe.md", summary)
        for line in summary.splitlines():
            if line.startswith("| run-"):
                cells = line.replace("\\|", "").split("|")
                self.assertEqual(len(cells), 5, line)


class DiffTests(unittest.TestCase):
    event = {"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}

    def test_missing_or_mismatched_merge_metadata_falls_back(self):
        for parents in (b"", b"head", b"different head", b"base head extra"):
            self.assertIsNone(changed_paths(self.event, git=Mock(return_value=parents)))
        self.assertIsNone(changed_paths({}, git=Mock()))
        self.assertIsNone(changed_paths(self.event, git=Mock(side_effect=OSError())))

    def test_diff_errors_and_malformed_output_fall_back(self):
        for error in (
            subprocess.CalledProcessError(1, "git"),
            raw_record("valid.md")[:-1],
            raw_record("valid.md") + b":100644 100644\0",
            b"not a record\0name\0",
            f":100644 100644 {SHA} {SHA} M\0bad-".encode() + b"\xff\0",
            f":100644 100644 {SHA} {SHA} M\0\0".encode(),
        ):
            with self.subTest(error=error):
                git = Mock(side_effect=[b"base head", error])
                self.assertIsNone(changed_paths(self.event, git=git))

    def test_raw_modes_mark_symlinks_and_submodules(self):
        for old, new, regular in (
            ("100644", "100644", True),
            ("100755", "100644", True),
            ("000000", "100755", True),
            ("100644", "000000", True),
            ("100644", "120000", False),
            ("120000", "000000", False),
            ("000000", "160000", False),
            ("160000", "160000", False),
        ):
            with self.subTest(old=old, new=new):
                self.assertEqual(
                    parse_raw_diff(raw_record("x.md", old, new)),
                    [ChangedPath("x.md", regular)],
                )
        self.assertEqual(parse_raw_diff(b""), [])

    def test_no_file_count_limit_and_literal_filenames(self):
        names = [f"lib/pymedphys/docs/page-{number}.md" for number in range(4000)]
        names += [
            "lib/pymedphys/docs/line\nbreak.md",
            "lib/pymedphys/docs/$(command).md",
            "lib/pymedphys/deleted.py",
        ]
        git = Mock(
            side_effect=[b"base head", b"".join(raw_record(name) for name in names)]
        )
        result = changed_paths(self.event, git=git)
        self.assertEqual([change.name for change in result], names)
        self.assertTrue(all(change.regular for change in result))
        self.assertTrue(select_checks(result)["run-python"])

    def test_real_merge_keeps_deletions_and_both_sides_of_renames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return git_in(root, *args)

            git("init", "-b", "main")
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
            changes = changed_paths(event, git=lambda args: git(*args[1:]))
            self.assertEqual(
                set(changes),
                {
                    ChangedPath("code.py"),
                    ChangedPath("README.rst"),
                    ChangedPath("deleted.py"),
                },
            )
            self.assertEqual(selected(select_checks(changes)), set(STANDARD))
            # Exercise the exact shallow history used by Actions, without a
            # network or an API response that could truncate the changed files.
            with tempfile.TemporaryDirectory() as checkout:
                git("clone", "--depth=2", "--no-local", root.as_uri(), checkout)

                def shallow_git(args):
                    return git_in(checkout, *args[1:])

                self.assertEqual(
                    shallow_git(["git", "rev-parse", "--is-shallow-repository"]),
                    b"true\n",
                )
                self.assertEqual(changed_paths(event, git=shallow_git), changes)

    def test_real_merge_marks_symlinks_and_submodules(self):
        # Build the trees with plumbing, so no platform needs symlink support.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git_in(root, "init", "-q")

            def blob(content: bytes) -> bytes:
                return git_in(root, "hash-object", "-w", "--stdin", stdin=content)

            def commit(entries: Mapping[str, tuple[str, bytes]], *parents: str) -> str:
                index = root / f"index-{len(parents)}"
                records = b"".join(
                    f"{mode} {sha.decode().strip()}\t{name}\0".encode()
                    for name, (mode, sha) in entries.items()
                )
                git_in(
                    root,
                    "update-index",
                    "-z",
                    "--add",
                    "--index-info",
                    stdin=records,
                    index=index,
                )
                tree = git_in(root, "write-tree", index=index).decode().strip()
                arguments = [argument for p in parents for argument in ("-p", p)]
                return (
                    git_in(root, "commit-tree", tree, *arguments, "-m", "commit")
                    .decode()
                    .strip()
                )

            text = blob(b"text\n")
            base = commit(
                {
                    "lib/pymedphys/docs/page.md": ("100644", text),
                    "lib/pymedphys/docs/other.md": ("100644", text),
                }
            )
            changed = {
                # A page that becomes a link can expose any file to the build.
                "lib/pymedphys/docs/page.md": ("120000", blob(b"../../../uv.lock")),
                "lib/pymedphys/docs/vendored.md": ("160000", text),
                "lib/pymedphys/docs/other.md": ("100644", blob(b"edited\n")),
            }
            head = commit(changed, base)
            git_in(root, "update-ref", "HEAD", commit(changed, base, head))
            event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}

            changes = changed_paths(event, git=lambda args: git_in(root, *args[1:]))

            self.assertEqual(
                sorted(changes),
                [
                    ChangedPath("lib/pymedphys/docs/other.md", True),
                    ChangedPath("lib/pymedphys/docs/page.md", False),
                    ChangedPath("lib/pymedphys/docs/vendored.md", False),
                ],
            )
            self.assertEqual(selected(select_checks(changes)), set(PATH_SELECTABLE))
            regular = [change for change in changes if change.regular]
            self.assertEqual(selected(select_checks(regular)), {"run-docs"})


if __name__ == "__main__":
    unittest.main()
