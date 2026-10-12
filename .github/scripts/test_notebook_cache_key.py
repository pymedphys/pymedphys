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

"""Executed notebooks are reused only when no execution input has changed."""

import os
import subprocess
import unittest
from pathlib import Path

from notebook_cache_key import DOC_ROOT, cache_key, is_prose, tracked_entries

REPOSITORY = Path(__file__).resolve().parents[2]


def entry(path: str, blob: str = "0" * 40) -> str:
    return f"100644 {blob} 0\t{path}"


BASE = {
    "pyproject.toml": entry("pyproject.toml"),
    "uv.lock": entry("uv.lock"),
    "module": entry("lib/pymedphys/_gamma/implementation.py"),
    "manifest": entry("lib/pymedphys/_data/hashes.json"),
    "notebook": entry(f"{DOC_ROOT}users/howto/gamma/from-dicom.ipynb"),
    "config": entry(f"{DOC_ROOT}_config.yml"),
    "rst": entry(f"{DOC_ROOT}users/index.rst"),
    "md": entry(f"{DOC_ROOT}users/overview.md"),
    "myst-notebook": entry(f"{DOC_ROOT}users/executed.md"),
}
HEADS = {f"{DOC_ROOT}users/executed.md": b"---\njupytext:\n"}
ENVIRONMENT = {"ImageOS": "ubuntu24", "ImageVersion": "20260920.1"}


def key(entries=None, interpreter="3.12.14", environment=None) -> str:
    return cache_key(
        (entries if entries is not None else BASE).values(),
        lambda path: HEADS.get(path, b"# Heading"),
        interpreter,
        environment if environment is not None else ENVIRONMENT,
    )


class CacheKeyTests(unittest.TestCase):
    def test_execution_inputs_change_the_key(self):
        for name in (
            "pyproject.toml",
            "uv.lock",
            "module",
            "manifest",
            "notebook",
            "config",
            "myst-notebook",
        ):
            with self.subTest(input=name):
                changed = dict(BASE)
                changed[name] = changed[name].replace("0" * 40, "1" * 40)
                self.assertNotEqual(key(changed), key())

    def test_added_and_removed_inputs_change_the_key(self):
        added = dict(BASE, data=entry(f"{DOC_ROOT}users/howto/gamma/data.csv"))
        removed = {name: value for name, value in BASE.items() if name != "module"}
        self.assertNotEqual(key(added), key())
        self.assertNotEqual(key(removed), key())

    def test_prose_does_not_change_the_key(self):
        for name in ("rst", "md"):
            with self.subTest(page=name):
                changed = dict(BASE)
                changed[name] = changed[name].replace("0" * 40, "1" * 40)
                self.assertEqual(key(changed), key())

    def test_only_documentation_prose_is_exempt(self):
        def read_head(_path):
            return b"# Heading"

        self.assertTrue(is_prose(f"{DOC_ROOT}page.md", read_head))
        self.assertTrue(is_prose(f"{DOC_ROOT}page.rst", read_head))
        self.assertFalse(is_prose(f"{DOC_ROOT}page.ipynb", read_head))
        self.assertFalse(is_prose(f"{DOC_ROOT}page.py", read_head))
        self.assertFalse(is_prose("lib/pymedphys/_data/README.md", read_head))
        self.assertFalse(is_prose(f"{DOC_ROOT}notebook.md", lambda _path: b"---"))

    def test_interpreter_and_runner_image_change_the_key(self):
        self.assertNotEqual(key(interpreter="3.12.15"), key())
        self.assertNotEqual(
            key(environment=dict(ENVIRONMENT, ImageVersion="20260927.1")), key()
        )


class RepositoryTests(unittest.TestCase):
    def test_every_notebook_and_the_build_configuration_are_inputs(self):
        cwd = os.getcwd()
        os.chdir(REPOSITORY)
        try:
            paths = [record.split("\t", 1)[1] for record in tracked_entries()]
            notebooks = subprocess.check_output(
                ["git", "ls-files", "--", f"{DOC_ROOT}*.ipynb"], text=True
            ).split()
        finally:
            os.chdir(cwd)
        self.assertTrue(notebooks)
        self.assertLessEqual(set(notebooks), set(paths))
        self.assertIn(f"{DOC_ROOT}_config.yml", paths)
        self.assertIn("uv.lock", paths)


if __name__ == "__main__":
    unittest.main()
