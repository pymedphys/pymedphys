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

"""Exercise migration failures that a successful Sphinx build can overlook."""

import tempfile
import unittest
from pathlib import Path

from check_documentation_migration import check


class MigrationTests(unittest.TestCase):
    def test_duplicate_controls_and_thebe_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "index.html"
            controls = (
                '<button class="sidebar-toggle primary-toggle">Navigation</button>'
                '<button class="secondary-toggle sidebar-toggle">Contents</button>'
            )
            config = '<script>const THEBE_JS_URL = "thebe.js";</script>'
            manifest = {"pages": []}
            page.write_text(controls + config, encoding="utf-8")
            self.assertEqual(check(root, manifest), [])
            page.write_text(controls + controls + config + config, encoding="utf-8")
            self.assertEqual(
                check(root, manifest),
                [
                    "index.html: duplicate primary-toggle controls",
                    "index.html: duplicate secondary-toggle controls",
                    "index.html: repeated inline THEBE_JS_URL declaration",
                ],
            )

    def test_prose_and_external_scripts_are_not_inline_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<p>const THEBE_JS_URL = "example";</p>'
                '<script src="https://example.com/thebe.js"></script>'
                '<script>const THEBE_JS_URL = "thebe.js";</script>'
                '<script>const other_config = "preserved";</script>',
                encoding="utf-8",
            )
            self.assertEqual(check(root, {"pages": []}), [])

    def test_retained_fragments_and_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<a href="old.html#original">old</a><a href="bundle.csv">data</a>'
                '<a href="https://example.com/no-local-file">external</a>',
                encoding="utf-8",
            )
            (root / "old.html").write_text('<span id="original"></span>')
            (root / "bundle.csv").write_text("x,y\n1,2\n")
            manifest = {
                "pages": [
                    {
                        "old_url": "old.html",
                        "fragments": ["original"],
                        "destination": "index.html",
                    }
                ]
            }
            self.assertEqual(check(root, manifest), [])
            (root / "old.html").write_text('<span id="renamed"></span>')
            (root / "bundle.csv").unlink()
            failures = check(root, manifest)
            self.assertIn("Retained fragment missing: old.html#original", failures)
            self.assertIn("index.html: missing target: bundle.csv", failures)
            self.assertIn("index.html: missing fragment: old.html#original", failures)

    def test_directory_links_encoded_fragments_and_missing_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide").mkdir()
            (root / "index.html").write_text('<a href="guide/#two%20words">guide</a>')
            (root / "guide/index.html").write_text('<span id="two words"></span>')
            manifest = {
                "pages": [
                    {
                        "old_url": "lost.html",
                        "fragments": [],
                        "destination": "index.html",
                    }
                ]
            }
            self.assertEqual(
                check(root, manifest), ["Retained page missing: lost.html"]
            )


if __name__ == "__main__":
    unittest.main()
