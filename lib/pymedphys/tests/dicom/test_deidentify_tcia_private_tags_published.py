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

"""The shipped TCIA Private Tag Dictionary, checked against TCIA's original.

These tests reach TCIA's site. They fail when TCIA's file no longer matches
the shipped copy, when TCIA's page links another file, or when the page no
longer names the licence that the shipped notice relies on; any of these
needs a review before the shipped copy or its notice changes.
"""

import hashlib
import html
import re

from pymedphys._imports import pytest

from pymedphys._data.download import download_with_progress
from pymedphys._dicom.deidentify import tcia_private_tags

PIN = tcia_private_tags.PIN
LICENCE_URL = "https://creativecommons.org/licenses/by/3.0/"


@pytest.mark.slow
def test_the_shipped_file_is_byte_for_byte_tcias_file(tmp_path):
    published = tmp_path / PIN.file_name
    download_with_progress(PIN.url, published)
    content = published.read_bytes()

    assert len(content) == PIN.size
    assert hashlib.sha256(content).hexdigest() == PIN.sha256
    assert content == (tcia_private_tags.TCIA_DIR / PIN.file_name).read_bytes()


@pytest.mark.slow
def test_tcias_page_links_the_pinned_file_under_its_licence(tmp_path):
    page = tmp_path / "page.html"
    download_with_progress(PIN.page_url, page)
    text = html.unescape(page.read_text("utf-8"))

    # The page links this version of the file, and no other edition of it.
    assert PIN.url in text
    assert set(re.findall(r"TCIAPrivateTagKB[^/?\"'<>\s]*", text)) == {PIN.file_name}
    assert LICENCE_URL in text
    assert "The Cancer Imaging Archive (TCIA)" in text
