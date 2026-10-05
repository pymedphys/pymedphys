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

"""Check retained URLs, local links and generated documentation controls."""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    """Read IDs and navigable links without a browser or third-party packages."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.links = []
        self.sidebar_toggles = {"primary-toggle": 0, "secondary-toggle": 0}
        self.thebe_declarations = 0
        self._inline_script = None
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag in {"img", "script", "source"} and attributes.get("src"):
            self.links.append(attributes["src"])
        if tag == "link" and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag == "button":
            for name in attributes.get("class", "").split():
                if name in self.sidebar_toggles:
                    self.sidebar_toggles[name] += 1
        if tag == "script" and not attributes.get("src"):
            self._inline_script = []

    def handle_data(self, data):
        if self._inline_script is not None:
            self._inline_script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._inline_script is not None:
            self.thebe_declarations += len(
                re.findall(r"\bconst\s+THEBE_JS_URL\s*=", "".join(self._inline_script))
            )
            self._inline_script = None


def check(build, manifest):
    """Return independently missing URLs/fragments and broken local links."""
    build = build.resolve()
    pages = {
        path.resolve(): Page(path)
        for path in build.rglob("*.html")
        if "_static" not in path.relative_to(build).parts
    }
    failures = set()

    def target(origin, href):
        parts = urlsplit(href)
        if parts.scheme or parts.netloc or parts.path.startswith("/"):
            return
        path = (origin.parent / unquote(parts.path)).resolve() if parts.path else origin
        if path.is_dir():
            path /= "index.html"
        if not path.is_relative_to(build):
            failures.add(f"{origin.relative_to(build)}: link escapes build: {href}")
        elif not path.exists():
            failures.add(f"{origin.relative_to(build)}: missing target: {href}")
        elif parts.fragment and path.suffix == ".html":
            fragment = unquote(parts.fragment)
            if path not in pages or fragment not in pages[path].ids:
                failures.add(f"{origin.relative_to(build)}: missing fragment: {href}")

    for entry in manifest["pages"]:
        path = (build / entry["old_url"]).resolve()
        if not path.is_relative_to(build) or path not in pages:
            failures.add(f"Retained page missing: {entry['old_url']}")
            continue
        for fragment in entry["fragments"]:
            if fragment not in pages[path].ids:
                failures.add(
                    f"Retained fragment missing: {entry['old_url']}#{fragment}"
                )
        target(build / "index.html", entry["destination"])
    for path, page in pages.items():
        # The installed theme binds only the first toggle of each kind. A
        # hidden duplicate silently leaves the visible control unresponsive.
        for name, count in page.sidebar_toggles.items():
            if count > 1:
                failures.add(f"{path.relative_to(build)}: duplicate {name} controls")
        # Redeclaring a top-level const is a browser SyntaxError even when
        # Sphinx renders the page successfully.
        if page.thebe_declarations > 1:
            failures.add(
                f"{path.relative_to(build)}: repeated inline THEBE_JS_URL declaration"
            )
        for href in page.links:
            target(path, href)
    return sorted(failures)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="Built HTML directory")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "lib/pymedphys/docs/project/documentation-migration.json",
    )
    args = parser.parse_args(argv)
    if not (args.build / "index.html").is_file():
        parser.error("The HTML build must contain index.html")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures = check(args.build, manifest)
    for failure in failures:
        print(failure)
    if not failures:
        print(
            f"Validated {len(manifest['pages'])} retained pages, local HTML links "
            "and generated controls."
        )
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
