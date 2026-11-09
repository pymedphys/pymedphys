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

"""An Encapsulated PDF's pages are rendered as printed (D-061).

A completed AcroForm's saved field values and ticked boxes, which PDFium
draws only through a form-filling environment, are rendered where they lie,
previewed, and released; a page is rendered at its size as printed, which
its UserUnit multiplies; and an XFA form, or a UserUnit that is not one
positive number, is refused; and an image-only PDF is read back as pages
only where it holds nothing but their images. The release path itself is
tested in
``test_deidentify_encapsulated_pdf_release``.
"""

import json
import math
import re
import zlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify.encapsulated_documents import (
    RENDER_DPI,
    DocumentRefused,
    rendered_pages,
    written_pages,
)
from pymedphys._dicom.deidentify.image_pdf import image_only_pdf
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.qc_previews import decoded_png
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review

from . import _synthetic_references as synthetic
from .test_deidentify_encapsulated_pdf import PAGE_SENTINEL, _encapsulated_pdf
from .test_deidentify_encapsulated_pdf_release import (
    LETTER,
    Finder,
    _file,
    _letter,
    _pdf,
    _random_pages,
    _rows_columns,
    _run,
    _transform,
    _write,
)
from .test_deidentify_redaction_review import _attest

# De-identification is private code, and pypdfium2 is in the user extra,
# not the dicom extra.
pytest.importorskip("pypdfium2")

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]


# A completed AcroForm on a US Letter page: a text field whose saved value
# is drawn by its normal appearance, a ticked check box, and an unticked
# one. Each Rect is in points from the bottom left of the page.
TEXT_FIELD = (100, 600, 200, 620)
TICKED = (100, 500, 112, 512)
UNTICKED = (150, 500, 162, 512)


def _appearance(width, height, content, resources=b""):
    return (
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 %d %d]%s /Length %d >>\nstream\n%s\nendstream"
        % (
            width,
            height,
            resources,
            len(content),
            content,
        )
    )


def _form_pdf():
    """Return a one-page PDF whose content is only its AcroForm's fields."""

    def rect(box):
        return b"[%d %d %d %d]" % box

    value = b"BT /Helv 14 Tf 4 4 Td (42) Tj ET"
    tick = b"0 0 0 rg 0 0 12 12 re f"
    return _file(
        [
            b"<< /Type /Catalog /Pages 2 0 R "
            b"/AcroForm << /Fields [4 0 R 5 0 R 6 0 R] >> >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Annots [4 0 R 5 0 R 6 0 R] >>",
            b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (value) /V (42) "
            b"/F 4 /P 3 0 R /Rect %s /AP << /N 7 0 R >> >>" % rect(TEXT_FIELD),
            b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (ticked) /V /Yes "
            b"/AS /Yes /F 4 /P 3 0 R /Rect %s /AP << /N << /Yes 8 0 R /Off 9 0 R >> >> >>"
            % rect(TICKED),
            b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (unticked) /V /Off "
            b"/AS /Off /F 4 /P 3 0 R /Rect %s /AP << /N << /Yes 8 0 R /Off 9 0 R >> >> >>"
            % rect(UNTICKED),
            _appearance(
                100,
                20,
                value,
                b" /Resources << /Font << /Helv 10 0 R >> >>",
            ),
            _appearance(12, 12, tick),
            _appearance(12, 12, b""),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    )


def _pixels(box, unit=1):
    """The rows and columns, as slices, that a Rect in points covers on a US
    Letter page of UserUnit ``unit`` at the resolution, computed here from
    the Rect alone, so that it checks the renderer independently."""
    scale = RENDER_DPI * unit / 72
    left, bottom, right, top = box
    rows = slice(math.floor((792 - top) * scale), math.ceil((792 - bottom) * scale))
    columns = slice(math.floor(left * scale), math.ceil(right * scale))
    return rows, columns


def _dark(page):
    return page.min(axis=-1) < 128


def _assert_form_drawn(page):
    """The saved value and the tick are drawn in their fields, and nothing
    else is drawn: not the unticked box, nor anything outside the fields."""
    dark = _dark(page)
    value = _pixels(TEXT_FIELD)
    ticked = _pixels(TICKED)
    assert dark[value].sum() > 50
    # The tick fills its 12-point box, 25 pixels square.
    assert dark[ticked].sum() >= 24 * 24
    assert not dark[_pixels(UNTICKED)].any()
    outside = dark.copy()
    outside[value] = False
    outside[ticked] = False
    assert not outside.any()


def _object_stream_pdf(page):
    """Return a PDF 1.5 whose catalogue, page tree, and ``page`` dictionary
    are compressed in an object stream, with a cross-reference stream."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page,
    ]
    header = b""
    body = b""
    for number, item in enumerate(objects, start=1):
        header += b"%d %d " % (number, len(body))
        body += item + b"\n"
    packed = zlib.compress(header + body)
    data = bytearray(b"%PDF-1.5\n")
    stream_offset = len(data)
    data += (
        b"4 0 obj\n<< /Type /ObjStm /N 3 /First %d /Filter /FlateDecode "
        b"/Length %d >>\nstream\n"
        % (len(header), len(packed))
        + packed
        + b"\nendstream\nendobj\n"
    )
    xref_offset = len(data)
    rows = [(0, 0, 65535), *((2, 4, index) for index in range(3))]
    rows += [(1, stream_offset, 0), (1, xref_offset, 0)]
    table = zlib.compress(
        b"".join(
            bytes([kind]) + first.to_bytes(4, "big") + second.to_bytes(2, "big")
            for kind, first, second in rows
        )
    )
    data += (
        b"5 0 obj\n<< /Type /XRef /Size 6 /W [1 4 2] /Root 1 0 R "
        b"/Filter /FlateDecode /Length %d >>\nstream\n"
        % len(table)
        + table
        + b"\nendstream\nendobj\n"
    )
    data += b"startxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(data)


def _unit_page(unit=b"", extra=()):
    """A US Letter page with a filled bar one inch long in default units,
    from 72 to 144 points across and 72 points below the top, its UserUnit
    entry, if any, as ``unit``, and ``extra`` objects numbered from 5."""
    content = b"0 0 0 rg 72 700 72 20 re f"
    return _file(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]%s "
            b"/Contents 4 0 R >>" % unit,
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
            *extra,
        ]
    )


def _assert_printed_size(pages, written, unit, rows, columns, *, bar):
    """The page written at the resolution is its size as printed, to within
    the part of a pixel by which its last row and column were rounded up,
    and, with ``bar``, :func:`_unit_page`'s bar, one inch long in default
    units, is UserUnit inches long as printed, in the page rendered and in
    the PDF written, to within the pixel at each end that its edges can blur
    into."""
    (media_box,) = re.findall(rb"/MediaBox \[([^\]]*)\]", written)
    _, _, width, height = (float(value) for value in media_box.split())
    pixel = 72 / RENDER_DPI
    assert 612 * unit <= width < 612 * unit + pixel
    assert 792 * unit <= height < 792 * unit + pixel
    assert pages.shape == (1, rows, columns, 3)
    if bar:
        row = math.floor((792 - 710) * unit * RENDER_DPI / 72)
        dark = np.flatnonzero(_dark(pages[0, row]))
        drawn = dark[-1] - dark[0] + 1
        assert abs(drawn - unit * RENDER_DPI) <= 2
        assert abs(drawn * width / columns - 72 * unit) <= 2 * pixel


# An annotation whose text quotes a UserUnit, away from the bar.
_QUOTED_UNIT = (
    b" /Annots [<< /Type /Annot /Subtype /Square /Rect [400 100 450 150] "
    b"/Contents (/UserUnit 3/) >>]"
)


# Rendering.


def test_a_forms_saved_values_and_ticked_boxes_are_rendered_where_they_lie():
    (page,) = rendered_pages(_form_pdf())

    assert page.shape == (*_rows_columns(*LETTER), 3)
    _assert_form_drawn(page)


@pytest.mark.parametrize(
    "unit, document",
    [
        (2, _unit_page(b" /UserUnit 2")),
        (2.5, _unit_page(b" /UserUnit 2.5")),
        # An escaped name is the same name (ISO 32000-1 Section 7.3.5).
        (2, _unit_page(b" /User#55nit 2")),
        (1, _unit_page(b" /UserUnit 1")),
        (1, _unit_page()),
        # A reference to no object is null, as if the entry were absent
        # (ISO 32000-1 Section 7.3.10), and PDFium writes no entry for it.
        (1, _unit_page(b" /UserUnit 5 0 R")),
        # A reference to a number.
        (2, _unit_page(b" /UserUnit 5 0 R", [b"2"])),
        # Beside an annotation whose text quotes another UserUnit.
        (1, _unit_page(_QUOTED_UNIT)),
        (1, _unit_page(_QUOTED_UNIT + b" /UserUnit 1")),
        (2, _unit_page(_QUOTED_UNIT + b" /UserUnit 2")),
        # A page dictionary compressed in an object stream.
        (
            2,
            _object_stream_pdf(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /UserUnit 2 >>"
            ),
        ),
    ],
    ids=[
        "2",
        "2.5",
        "escaped",
        "1",
        "none",
        "dangling",
        "reference",
        "quoted-absent",
        "quoted-default",
        "quoted-2",
        "object-stream",
    ],
)
def test_a_page_is_rendered_and_written_at_its_physical_size(unit, document):
    pages = rendered_pages(document)

    # 8.5 by 11 inches in default units, each of which is UserUnit / 72 inch.
    rows, columns = (
        math.ceil(11 * unit * RENDER_DPI),
        math.ceil(8.5 * unit * RENDER_DPI),
    )
    assert pages.shape == (1, rows, columns, 3)
    _assert_printed_size(
        pages,
        image_only_pdf(pages, RENDER_DPI),
        unit,
        rows,
        columns,
        bar=b"/Contents" in document,
    )


@pytest.mark.parametrize(
    "document",
    [
        _unit_page(b" /UserUnit 0"),
        _unit_page(b" /UserUnit -2"),
        _unit_page(b" /UserUnit 5 0 R", [b"(2)"]),
        _unit_page(b" /UserUnit (2)"),
        _file(
            [
                b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] "
                b"/XFA (<xdp:xdp/>) /NeedsRendering true >> >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
            ]
        ),
        _file(
            [
                b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] "
                b"/XFA (<xdp:xdp/>) >> >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
            ]
        ),
    ],
    ids=[
        "unit-0",
        "unit-negative",
        "unit-reference-to-string",
        "unit-string",
        "xfa",
        "xfa-static",
    ],
)
def test_a_page_unit_or_form_that_cannot_be_drawn_as_printed_is_refused(document):
    with pytest.raises(DocumentRefused) as refused:
        rendered_pages(document)

    assert refused.value.reason is TransformReason.UNCLEANABLE_DOCUMENT


def test_the_xfa_test_documents_are_xfa_forms_to_pdfium():
    # So that their refusal above is the engine's check of the form's type.
    import pypdfium2  # pylint: disable = import-outside-toplevel

    for needs_rendering in (b" /NeedsRendering true", b""):
        pdf = pypdfium2.PdfDocument(
            _file(
                [
                    b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] "
                    b"/XFA (<xdp:xdp/>)%s >> >>" % needs_rendering,
                    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
                ]
            )
        )
        try:
            assert pdf.get_formtype() in (
                pypdfium2.raw.FORMTYPE_XFA_FULL,
                pypdfium2.raw.FORMTYPE_XFA_FOREGROUND,
            )
        finally:
            pdf.close()


# Reading back the image-only PDF.


def test_a_document_with_text_or_another_form_does_not_read_back_as_pages():
    pages = _random_pages(2, 4, 6)
    document = image_only_pdf(pages, RENDER_DPI)
    # An annotation added to the first page.
    annotated = document.replace(
        b"/Contents 4 0 R >>",
        b"/Contents 4 0 R /Annots [<< /Type /Annot /Subtype /Square "
        b"/Rect [0 0 1 1] >>] >>",
    )
    for wrong in (
        (_pdf([_letter((72, 700, PAGE_SENTINEL))]), 1, *_rows_columns(*LETTER)),
        (document, 1, 4, 6),
        (document, 3, 4, 6),
        (document, 2, 6, 4),
        (document, 2, 4, 5),
        (b"not a document", 2, 4, 6),
    ):
        with pytest.raises(DocumentRefused) as refused:
            written_pages(*wrong)
        assert refused.value.reason is TransformReason.REDACTION_MISMATCH
    assert np.array_equal(written_pages(document, 2, 4, 6), pages)
    # The annotated copy is still a PDF, but is refused, as is a copy with a
    # form, whose fields would be drawn over its pages.
    with_form = document.replace(
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] >> >>",
    )
    for changed in (annotated, with_form):
        assert changed != document
        with pytest.raises(DocumentRefused):
            written_pages(_with_xref(changed), 2, 4, 6)


def _with_xref(document):
    """Return a document rewritten with its cross-reference table counted
    again, after an object was changed in place."""
    objects = re.findall(rb"\d+ 0 obj\n(.*?)\nendobj\n", document, re.DOTALL)
    return _file(objects)


# Previewed, reviewed, and released.


def _reviewed_and_released(directory, document):
    """Run an Encapsulated PDF holding ``document`` twice, with no text
    found: the first run holds it, a reviewer accepts it, and the second
    releases it. Return the page as previewed, its review frame, and the
    document released."""
    dataset = _encapsulated_pdf()
    dataset.EncapsulatedDocument = document
    dataset.EncapsulatedDocumentLength = len(document)
    _write(directory / "source", {"document.dcm": synthetic.written(dataset)})

    first = _run(
        directory / "first", directory / "source", _transform(finder=Finder(()))
    )
    pack = first.qc_pack.parent
    held = json.loads(first.qc_pack.read_text("utf-8"))
    (entry,) = held["instances"]
    assert entry["disposition"] == "held-for-review"
    (redaction,) = held["redactions"]
    assert redaction["reason"] == "no-text-found"
    images = {
        preview["kind"]: decoded_png((pack / preview["file"]).read_bytes())
        for preview in held["previews"]
    }

    _attest(pack, (RedactionVerdict(entry["position"], Redaction.ACCEPTED),))
    second = _run(
        directory / "second",
        directory / "source",
        _transform(finder=Finder(()), redaction_review=read_redaction_review(pack)),
    )
    (released,) = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
    assert released["disposition"] == "released"
    written = pydicom.dcmread(
        directory / "second" / "release" / released["output"], force=True
    )
    return (
        images["redaction"],
        images["review-frame"],
        bytes(written.EncapsulatedDocument),
    )


def test_a_forms_saved_fields_are_previewed_reviewed_and_released(tmp_path):
    preview, review_frame, released = _reviewed_and_released(tmp_path, _form_pdf())

    # The page as previewed, as the review app shows it, and as released.
    _assert_form_drawn(preview)
    _assert_form_drawn(review_frame)
    (page,) = written_pages(released, 1, *_rows_columns(*LETTER))
    _assert_form_drawn(page)


@pytest.mark.parametrize(
    "unit, entry",
    [(1, b""), (1, b" /UserUnit 1"), (2, b" /UserUnit 2")],
    ids=["absent", "default", "two"],
)
def test_a_page_beside_annotation_text_is_released_at_its_printed_size(
    tmp_path, unit, entry
):
    # The annotation quotes another UserUnit, which is not the page's.
    document = _unit_page(_QUOTED_UNIT + entry)
    preview, review_frame, released = _reviewed_and_released(tmp_path, document)

    rows, columns = (
        math.ceil(11 * unit * RENDER_DPI),
        math.ceil(8.5 * unit * RENDER_DPI),
    )
    assert review_frame.shape == preview.shape == (rows, columns, 3)
    (page,) = written_pages(released, 1, rows, columns)
    _assert_printed_size(page[None], released, unit, rows, columns, bar=True)
