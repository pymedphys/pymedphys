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

"""A page's UserUnit is read from its own dictionary alone (D-061).

These files are written here in the form in which PDFium saves a document
whole, with CRLF line ends, a cross-reference table, and no object stream,
so that :func:`.pdf_syntax.page_user_unit` is tested without PDFium.
"""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify.pdf_syntax import page_user_unit


def _saved(page, extra=(), trailer=b"/Root 1 0 R /Size %d"):
    """Return a one-page PDF whose page, object 3, is ``page``, with
    ``extra`` objects numbered from 4."""
    objects = [
        b"<</Pages 2 0 R /Type/Catalog>>",
        b"<</Count 1/Kids[ 3 0 R ]/Type/Pages>>",
        page,
        *extra,
    ]
    data = bytearray(b"%PDF-1.7\r\n%\xa1\xb3\xc5\xd7\r\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += b"%d 0 obj\r\n%s\r\nendobj\r\n" % (number, body)
    xref = len(data)
    data += b"xref\r\n0 %d\r\n0000000000 65535 f\r\n" % (len(objects) + 1)
    for offset in offsets:
        data += b"%010d 00000 n\r\n" % offset
    size = trailer % (len(objects) + 1) if b"%d" in trailer else trailer
    data += b"trailer\r\n<<\r\n%s>>\r\nstartxref\r\n%d\r\n%%%%EOF\r\n" % (size, xref)
    return bytes(data)


_PAGE = b"<</MediaBox[ 0 0 612 792]/Parent 2 0 R /Type/Page%s>>"


def _page(entries=b""):
    return _PAGE % entries


# Text that quotes PDF syntax, in places other than the page's own entry.
_QUOTED = (
    # An annotation's Contents, a literal string.
    b"/Annots[<</Contents(/UserUnit 2/)/Rect[ 0 0 1 1]/Subtype/Square/Type/Annot>>]",
    # With nested and escaped parentheses.
    b"/Annots[<</Contents(a \\( (b) /UserUnit 3 \\) c)/Subtype/Text>>]",
    # A hexadecimal string.
    b"/Annots[<</Contents</UserUnit 2>/Subtype/Text>>]",
    # A nested dictionary's own UserUnit entry.
    b"/Resources<</UserUnit 2>>",
)


@pytest.mark.parametrize("quoted", _QUOTED)
@pytest.mark.parametrize(
    "entry, unit",
    [(b"", 1.0), (b"/UserUnit 1", 1.0), (b"/UserUnit 2", 2.0)],
    ids=["absent", "default", "two"],
)
def test_only_the_pages_own_entry_is_read(quoted, entry, unit):
    assert page_user_unit(_saved(_page(quoted + entry))) == unit
    assert page_user_unit(_saved(_page(entry + quoted))) == unit


@pytest.mark.parametrize(
    "saved, unit",
    [
        (_saved(_page(b"/UserUnit 2.5")), 2.5),
        (_saved(_page(b"/UserUnit .5")), 0.5),
        (_saved(_page(b"/UserUnit +3")), 3.0),
        (_saved(_page(b"/User#55nit 2")), 2.0),
        (_saved(_page(b"/UserUnit null")), 1.0),
        # A comment is white space.
        (_saved(_page(b"%/UserUnit 2\r\n/UserUnit 3")), 3.0),
        # Through references, to a number.
        (_saved(_page(b"/UserUnit 4 0 R"), [b"2"]), 2.0),
        (_saved(_page(b"/UserUnit 4 0 R"), [b"5 0 R", b"2"]), 2.0),
        # A reference to no object is null.
        (_saved(_page(b"/UserUnit 9 0 R")), 1.0),
        # The page itself through a reference in the trailer's Root.
        (_saved(_page(b"/UserUnit 2"), trailer=b"/Size 4/Root 1 0 R"), 2.0),
    ],
    ids=[
        "decimal",
        "leading-point",
        "signed",
        "escaped-name",
        "null",
        "comment",
        "reference",
        "two-references",
        "dangling",
        "root-last",
    ],
)
def test_a_page_unit_is_read_as_its_syntax_gives_it(saved, unit):
    assert page_user_unit(saved) == unit


@pytest.mark.parametrize(
    "saved",
    [
        _saved(_page(b"/UserUnit 0")),
        _saved(_page(b"/UserUnit -2")),
        _saved(_page(b"/UserUnit (2)")),
        _saved(_page(b"/UserUnit true")),
        _saved(_page(b"/UserUnit/Two")),
        _saved(_page(b"/UserUnit[ 2]")),
        _saved(_page(b"/UserUnit 2x")),
        _saved(_page(b"/UserUnit 4 0 R"), [b"(2)"]),
        # A loop of references.
        _saved(_page(b"/UserUnit 4 0 R"), [b"5 0 R", b"4 0 R"]),
        # Unclosed, or nested too deeply.
        _saved(_page(b"/Annots[<</Contents(open>>]")),
        _saved(_page(b"/Annots" + b"[" * 100 + b"]" * 100)),
        # Not a page, or a page tree of more than one page.
        _saved(b"<</MediaBox[ 0 0 612 792]/Type/Pages>>"),
        _saved(_page()).replace(b"/Kids[ 3 0 R ]", b"/Kids[ 3 0 R 3 0 R ]"),
        # Not the file that PDFium writes.
        b"not a document",
        _saved(_page()).replace(b"xref\r\n", b"xrof\r\n"),
    ],
    ids=[
        "zero",
        "negative",
        "string",
        "boolean",
        "name",
        "array",
        "not-a-number",
        "reference-to-string",
        "reference-loop",
        "unclosed",
        "deep",
        "not-a-page",
        "two-kids",
        "not-pdf",
        "no-xref",
    ],
)
def test_a_page_unit_or_file_that_cannot_be_read_so_is_refused(saved):
    with pytest.raises(ValueError):
        page_user_unit(saved)
