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

"""Releasing an Encapsulated PDF's document as its reviewed rendering (D-061).

Under the Clean Pixel Data Option, an Encapsulated PDF's pages are rendered
in the decoding child, searched for text and blacked out as an image's
frames are, written as an image-only PDF, and held for review; a later run
given a reviewer's verdict releases the reviewed pages. Every document
here is synthetic, written by the tests, with invented text.
"""

import contextlib
import hashlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    document_cleaning,
    encapsulated_documents,
    instance_transform,
    isolated_decoding,
    markers,
    policy,
    run,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.document_cleaning import (
    clean_document,
    document_problem,
)
from pymedphys._dicom.deidentify.encapsulated_documents import (
    RENDER_DPI,
    DocumentRefused,
    rendered_pages,
    written_pages,
)
from pymedphys._dicom.deidentify.image_pdf import ImagePdfError, image_only_pdf
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    PixelsNotReviewed,
)
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.qc_previews import decoded_png
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    TransformReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.text_detection import TextBox
from pymedphys._dicom.deidentify.walker import SequesterReason

from . import _corpus_run
from . import _synthetic_references as synthetic
from .test_deidentify_encapsulated_pdf import (
    AUTHOR_SENTINEL,
    DOCUMENT,
    KEY,
    PAGE_SENTINEL,
    _encapsulated_pdf,
    _NoText,
    _policies,
)
from .test_deidentify_redaction_review import _attest

# De-identification is private code, and pypdfium2 is in the user extra,
# not the dicom extra.
pytest.importorskip("pypdfium2")

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

CLEAN_PIXEL_DATA = policy.CLEAN_PIXEL_DATA
CODE = "113101"
# Where the scope tests' document's 12-point text lies once rendered at 150
# pixels per inch, 72 points from the left and 72 below the top of a US
# Letter page: rows 131 to 151, columns 150 to 447.
BOX = TextBox(120, 140, 170, 700)
# Where these tests' 24-point text, 92 points below the top, lies: rows 155
# to 194, columns from 151.
BIG = TextBox(140, 140, 210, 1000)
# A reviewer's own region, in place of the finder's.
ADDED = TextBox(0, 0, 4, 6)
WHITE = 255


class Finder:
    """Gives fixed regions on every page, and records each page it sees."""

    method = {"finder": "fixed regions", "version": 1}

    def __init__(self, boxes=(BOX,)):
        self.boxes = tuple(boxes)
        self.seen = []

    def find(self, frame):
        self.seen.append(np.array(frame))
        return self.boxes


def _pdf(pages, *, trailer=b"", extra=()):
    """Return a PDF of ``pages``, each (width, height, rotate, lines), with
    each line (x, y, text) in Helvetica at 24 points, and ``extra`` objects
    numbered after the pages' and fonts'."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    for width, height, rotate, lines in pages:
        number = len(objects) + 1
        kids.append(b"%d 0 R" % number)
        rotation = b" /Rotate %d" % rotate if rotate else b""
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d]%s "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (width, height, rotation, number + 2, number + 1)
        )
        content = b"".join(
            b"BT /F1 24 Tf %d %d Td (%s) Tj ET\n" % (x, y, text.encode("ascii"))
            for x, y, text in lines
        )
        objects.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
        )
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(kids),
        len(kids),
    )
    objects.extend(extra)
    return _file(objects, trailer)


def _file(objects, trailer=b""):
    """Return a PDF of ``objects``, numbered from 1, with a cross-reference
    table, and a trailer naming the catalogue and holding ``trailer``."""
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f\r\n" % (len(objects) + 1)
    for offset in offsets:
        data += b"%010d 00000 n\r\n" % offset
    data += b"trailer\n<< /Size %d /Root 1 0 R %s>>\n" % (len(objects) + 1, trailer)
    data += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(data)


LETTER = (612, 792)


def _letter(*lines, rotate=0):
    return (*LETTER, rotate, lines)


def _rc4(key, data):
    """RC4, as the PDF Standard security handler of revision 2 uses it."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    i = j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        out.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(out)


# ISO 32000-1 Section 7.6.3.3, Algorithm 2's padding string.
_PADDING = bytes.fromhex(
    "28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A"
)


def _encrypted_pdf():
    """Return a PDF encrypted by the Standard security handler, revision 2,
    with an empty user password, so that it opens without one."""
    identifier = bytes(range(16))
    permissions = -4
    owner = _rc4(hashlib.md5(b"owner" + _PADDING[:27]).digest()[:5], _PADDING)
    key = hashlib.md5(
        _PADDING + owner + permissions.to_bytes(4, "little", signed=True) + identifier
    ).digest()[:5]
    user = _rc4(key, _PADDING)
    plain = _pdf([_letter((72, 700, "LOCKED"))])
    objects = re.findall(rb"\d+ 0 obj\n(.*?)\nendobj\n", plain, re.DOTALL)
    encrypt = b"<< /Filter /Standard /V 1 /R 2 /O <%s> /U <%s> /P %d >>" % (
        owner.hex().encode(),
        user.hex().encode(),
        permissions,
    )
    return _file(
        [*objects, encrypt],
        b"/Encrypt %d 0 R /ID [<%s> <%s>] "
        % (len(objects) + 1, identifier.hex().encode(), identifier.hex().encode()),
    )


def _rows_columns(width, height):
    return (
        -(-height * RENDER_DPI // 72),
        -(-width * RENDER_DPI // 72),
    )


def _transform(options=(CLEAN_PIXEL_DATA,), finder=None, **kwargs):
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        finder=Finder() if finder is None else finder,
        unvalidated_policy=True,
        **kwargs,
    )


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def _random_pages(count, rows, columns, seed=0):
    return np.random.default_rng(seed).integers(
        0, 256, (count, rows, columns, 3), dtype=np.uint8
    )


# The image-only PDF.


def test_an_image_only_pdf_reads_back_as_its_pages_exactly():
    # Odd rows and columns, sample for sample.
    pages = _random_pages(3, 7, 5)

    document = image_only_pdf(pages, RENDER_DPI)

    assert np.array_equal(written_pages(document, 3, 7, 5), pages)


def test_an_image_only_pdf_holds_only_its_pages_images():
    document = image_only_pdf(_random_pages(2, 4, 6), RENDER_DPI)

    assert document.startswith(b"%PDF-1.4\n")
    assert len(document) % 2 == 0
    for name in (
        b"/Info",
        b"/ID",
        b"/Metadata",
        b"/Annots",
        b"/Outlines",
        b"/Names",
        b"/EmbeddedFiles",
        b"/JavaScript",
        b"/JS",
        b"/OpenAction",
        b"/AA",
        b"/AcroForm",
        b"/Font",
        b"BT",
    ):
        assert name not in document, name
    assert document.count(b"/Subtype /Image") == 2
    # The same pages give the same bytes.
    assert document == image_only_pdf(_random_pages(2, 4, 6), RENDER_DPI)


def test_each_cross_reference_entry_gives_its_objects_offset():
    document = image_only_pdf(_random_pages(2, 4, 6), RENDER_DPI)
    start = int(document.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert document[start:].startswith(b"xref\n0 9\n")
    entries = document[start:].split(b"\n")[3:11]
    for number, entry in enumerate(entries, start=1):
        assert len(entry) == 19  # and its "\r" ends the 20 bytes with "\n"
        assert document[int(entry[:10]) :].startswith(b"%d 0 obj\n" % number)


@pytest.mark.parametrize(
    "pixels, points",
    [(150, b"72"), (1240, b"595.2"), (1275, b"612"), (1, b"0.48"), (25, b"12")],
)
def test_a_page_is_as_many_points_as_its_pixels_at_the_resolution(pixels, points):
    document = image_only_pdf([np.zeros((pixels, pixels, 3), np.uint8)], RENDER_DPI)

    assert b"/MediaBox [0 0 %s %s]" % (points, points) in document


@pytest.mark.parametrize(
    "pages, dpi",
    [
        ([], RENDER_DPI),
        ([np.zeros((2, 2, 3), np.uint16)], RENDER_DPI),
        ([np.zeros((2, 2), np.uint8)], RENDER_DPI),
        ([np.zeros((2, 2, 4), np.uint8)], RENDER_DPI),
        ([np.zeros((0, 2, 3), np.uint8)], RENDER_DPI),
        ([[[[0, 0, 0]]]], RENDER_DPI),
        ([np.zeros((2, 2, 3), np.uint8)], 0),
        ([np.zeros((2, 2, 3), np.uint8)], 7),
        ([np.zeros((2, 2, 3), np.uint8)], True),
    ],
)
def test_pages_that_are_not_rgb_images_are_refused(pages, dpi):
    with pytest.raises(ImagePdfError):
        image_only_pdf(pages, dpi)


# Rendering, in the decoding child.


def test_a_page_is_rendered_at_the_resolution_with_its_text_dark_on_white():
    pages = rendered_pages(_pdf([_letter((72, 700, PAGE_SENTINEL))]))

    rows, columns = _rows_columns(*LETTER)
    assert pages.shape == (1, rows, columns, 3)
    assert pages.dtype == np.uint8
    dark = np.argwhere(pages[0].min(axis=2) < 128)
    # The text lies where the page places it, and the rest of the page is
    # white.
    assert dark.size
    assert dark[:, 0].min() >= BIG.top and dark[:, 0].max() < BIG.bottom
    assert dark[:, 1].min() >= BIG.left and dark[:, 1].max() < BIG.right
    outside = pages[0].copy()
    outside[BIG.top : BIG.bottom, BIG.left : BIG.right] = WHITE
    assert (outside == WHITE).all()


def test_pages_of_different_sizes_are_padded_with_white_to_the_largest():
    small = (300, 400)
    pages = rendered_pages(
        _pdf([_letter((72, 700, "FIRST")), (*small, 0, ((20, 300, "SECOND"),))])
    )

    rows, columns = _rows_columns(*LETTER)
    small_rows, small_columns = _rows_columns(*small)
    assert pages.shape == (2, rows, columns, 3)
    assert (pages[1, small_rows:] == WHITE).all()
    assert (pages[1, :, small_columns:] == WHITE).all()
    assert (pages[1, :small_rows, :small_columns] < 128).any()


def test_a_rotated_page_is_rendered_as_a_viewer_shows_it():
    pages = rendered_pages(_pdf([_letter((72, 700, "TURNED"), rotate=90)]))

    rows, columns = _rows_columns(*LETTER)
    assert pages.shape == (1, columns, rows, 3)


@pytest.mark.parametrize(
    "document",
    [
        b"not a document",
        b"%PDF-1.4\n%%EOF\n",
        _file(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [] /Count 0 >>",
            ]
        ),
        _encrypted_pdf(),
    ],
    ids=["not-pdf", "empty", "no-page", "encrypted"],
)
def test_a_document_that_cannot_be_rendered_for_review_is_refused(document):
    with pytest.raises(DocumentRefused) as refused:
        rendered_pages(document)

    assert refused.value.reason is TransformReason.UNCLEANABLE_DOCUMENT


def test_the_encrypted_test_document_opens_without_a_password():
    # So that its refusal above is the engine's, not PDFium's.
    pdfium = pytest.importorskip("pypdfium2")
    pdf = pdfium.PdfDocument(_encrypted_pdf())
    try:
        assert len(pdf) == 1
        assert pdfium.raw.FPDF_GetSecurityHandlerRevision(pdf) == 2
    finally:
        pdf.close()


@pytest.mark.parametrize(
    "limit, value",
    [
        ("MAX_PAGES", 1),
        ("MAX_PAGE_PIXELS", 1000),
        ("MAX_DOCUMENT_BYTES", 100),
        ("MAX_RENDERED_BYTES", 1000),
    ],
)
def test_a_document_past_a_limit_is_refused(monkeypatch, limit, value):
    document = _pdf([_letter((72, 700, "ONE")), _letter((72, 700, "TWO"))])
    monkeypatch.setattr(encapsulated_documents, limit, value)

    with pytest.raises(DocumentRefused) as refused:
        rendered_pages(document)

    assert refused.value.reason is TransformReason.UNCLEANABLE_DOCUMENT


def test_a_document_is_refused_without_the_renderer(monkeypatch):
    monkeypatch.setattr(encapsulated_documents, "renderer_available", lambda: False)

    for read in (
        lambda: rendered_pages(_pdf([_letter()])),
        lambda: written_pages(image_only_pdf(_random_pages(1, 2, 2), 150), 1, 2, 2),
    ):
        with pytest.raises(DocumentRefused) as refused:
            read()
        assert refused.value.reason is TransformReason.NO_RENDERER


def test_a_document_is_refused_where_the_child_cannot_run(monkeypatch):
    def unavailable(*_, **__):
        raise isolated_decoding.DecoderUnavailable()

    monkeypatch.setattr(isolated_decoding, "run", unavailable)

    with pytest.raises(DocumentRefused) as refused:
        rendered_pages(_pdf([_letter()]))

    assert refused.value.reason is TransformReason.NO_RENDERER


@pytest.mark.parametrize(
    "sizes, page",
    [
        ("12", None),
        ([], None),
        ([[1, 1]] * 201, None),
        ([[1]], None),
        ([[0, 1]], None),
        ([[True, 1]], None),
        ([[1.0, 1]], None),
        ([[5000, 5000]], None),
        ([[1, 1]], 12),
        ([[1, 1]], "!!!!"),
        ([[1, 1]], "AAAAAAAA"),
        ([[1, 2]], "AAAA"),
    ],
)
def test_what_the_child_sends_back_is_checked(monkeypatch, sizes, page):
    def sent(task, *_, **__):
        return sizes if task.__name__ == "_page_sizes" else page

    monkeypatch.setattr(isolated_decoding, "run", sent)

    with pytest.raises(DocumentRefused) as refused:
        rendered_pages(_pdf([_letter()]))

    assert refused.value.reason is TransformReason.UNCLEANABLE_DOCUMENT


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
    # The annotated copy is still a PDF, but is refused.
    with pytest.raises(DocumentRefused):
        written_pages(_with_xref(annotated), 2, 4, 6)


def _with_xref(document):
    """Return a document rewritten with its cross-reference table counted
    again, after an object was changed in place."""
    objects = re.findall(rb"\d+ 0 obj\n(.*?)\nendobj\n", document, re.DOTALL)
    return _file(objects)


# Cleaning a document.


def _source(*pages):
    dataset = _encapsulated_pdf()
    document = _pdf(list(pages)) if pages else _pdf([_letter((72, 700, PAGE_SENTINEL))])
    dataset.EncapsulatedDocument = document
    dataset.EncapsulatedDocumentLength = len(document)
    return read_source(synthetic.written(dataset))


def test_the_finders_regions_are_blacked_out_on_each_rendered_page():
    finder = Finder((BOX, TextBox(10, 10, 20, 99999)))
    source = _source(_letter((72, 700, "ONE")), _letter((72, 700, "TWO")))

    cleaned = clean_document(source, finder)

    rendered = rendered_pages(source.value_field(DOCUMENT))
    assert len(finder.seen) == 2
    assert all(np.array_equal(seen, page) for seen, page in zip(finder.seen, rendered))
    columns = rendered.shape[2]
    clipped = TextBox(10, 10, 20, columns)
    assert [(each.frame, each.boxes) for each in cleaned.regions] == [
        (0, tuple(sorted((BOX, clipped)))),
        (1, tuple(sorted((BOX, clipped)))),
    ]
    expected = rendered.copy()
    for box in (BOX, clipped):
        expected[:, box.top : box.bottom, box.left : box.right] = 0
    assert np.array_equal(cleaned.written, expected)
    assert cleaned.decoded == rendered.tobytes()
    assert cleaned.decoded_sha256 == hashlib.sha256(rendered.tobytes()).digest()
    assert cleaned.value == image_only_pdf(expected, RENDER_DPI)
    assert (cleaned.layout.frames, cleaned.layout.samples) == (2, 3)
    assert cleaned.layout.photometric == "RGB"
    assert cleaned.reason is PixelDataReason.TEXT_BLACKED_OUT


def test_a_document_without_text_found_is_written_as_rendered():
    source = _source()

    cleaned = clean_document(source, Finder(()))

    assert not cleaned.regions
    assert cleaned.reason is PixelDataReason.NO_TEXT_FOUND
    assert cleaned.written.tobytes() == cleaned.decoded


def test_reviewed_regions_are_blacked_out_alone():
    source = _source()
    first = clean_document(source, Finder())
    finder = Finder()

    cleaned = clean_document(
        source,
        finder,
        reviewed=((0, (BOX, ADDED)),),
        decoded_sha256=first.decoded_sha256,
    )

    assert not finder.seen
    assert cleaned.regions[0].boxes == (ADDED, BOX)
    assert (
        cleaned.written[0, ADDED.top : ADDED.bottom, ADDED.left : ADDED.right] == 0
    ).all()


def test_reviewed_regions_need_the_pages_that_the_reviewer_saw():
    source = _source()

    for digest in (None, bytes(32)):
        with pytest.raises(PixelsNotReviewed):
            clean_document(source, None, reviewed=((0, (BOX,)),), decoded_sha256=digest)


@pytest.mark.parametrize(
    "regions",
    [((1, (BOX,)),), ((-1, (BOX,)),), ((0, (TextBox(0, 0, 1, 99999),)),)],
)
def test_a_reviewed_region_that_does_not_fit_the_pages_is_refused(regions):
    source = _source()
    digest = clean_document(source, Finder()).decoded_sha256

    with pytest.raises(PixelDataRefused) as refused:
        clean_document(source, None, reviewed=regions, decoded_sha256=digest)

    assert refused.value.reason is TransformReason.REDACTION_MISMATCH


def test_a_document_is_cleaned_by_a_finder_or_a_review():
    with pytest.raises(TypeError):
        clean_document(_source(), None)


def test_a_written_document_other_than_the_one_planned_is_found():
    cleaned = clean_document(_source(), Finder())
    dataset = _encapsulated_pdf()
    dataset.EncapsulatedDocument = cleaned.value
    dataset.EncapsulatedDocumentLength = len(cleaned.value)
    assert not document_problem(read_source(synthetic.written(dataset)), cleaned)

    other = image_only_pdf(cleaned.written[:, ::-1].copy(), RENDER_DPI)
    for changes in (
        {"EncapsulatedDocument": other},
        {"EncapsulatedDocumentLength": len(cleaned.value) + 2},
    ):
        changed = _encapsulated_pdf()
        changed.EncapsulatedDocument = cleaned.value
        changed.EncapsulatedDocumentLength = len(cleaned.value)
        for keyword, value in changes.items():
            setattr(changed, keyword, value)
        assert document_problem(read_source(synthetic.written(changed)), cleaned)
    del dataset.EncapsulatedDocument
    assert document_problem(read_source(synthetic.written(dataset)), cleaned)


def test_a_written_document_that_reads_back_otherwise_is_found(monkeypatch):
    cleaned = clean_document(_source(), Finder())
    dataset = _encapsulated_pdf()
    dataset.EncapsulatedDocument = cleaned.value
    dataset.EncapsulatedDocumentLength = len(cleaned.value)
    output = read_source(synthetic.written(dataset))
    monkeypatch.setattr(
        document_cleaning,
        "written_pages",
        lambda *_: np.zeros_like(cleaned.written),
    )

    assert document_problem(output, cleaned)


# The transform.


@pytest.mark.parametrize(
    "composed",
    [composed for composed in _policies() if CLEAN_PIXEL_DATA in composed.options],
    ids=lambda composed: ",".join(composed.options),
)
def test_every_policy_with_clean_pixel_data_holds_a_document_as_its_rendering(
    composed,
):
    """The counterpart, over the same policies, of the test that every other
    policy sequesters the document (D-010, D-061)."""
    data = synthetic.written(_encapsulated_pdf())
    transform = InstanceTransform(
        composed,
        KEY,
        cleaning=(
            DescriptorCleaning(None, ReviewedNames.empty())
            if "clean_descriptors" in composed.options
            else None
        ),
        finder=_NoText(),
        face_review=_corpus_run.face_review_for(composed),
        unvalidated_policy=True,
    )

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed)
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert HeldPixelData(PixelDataReason.NO_TEXT_FOUND) in held
    # With no text found, the document is written as its pages rendered.
    pages = rendered_pages(_encapsulated_pdf().EncapsulatedDocument)
    document = bytes(pydicom.dcmread(io.BytesIO(result.data)).EncapsulatedDocument)
    np.testing.assert_array_equal(written_pages(document, *pages.shape[:3]), pages)


def test_under_clean_pixel_data_a_document_is_written_as_its_cleaned_pages():
    finder = Finder()

    result = _transformed(_transform(finder=finder), _encapsulated_pdf())

    assert isinstance(result, run.Transformed)
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert held == (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),)
    written = pydicom.dcmread(io.BytesIO(result.data))
    document = bytes(written.EncapsulatedDocument)
    assert written.EncapsulatedDocumentLength == len(document)
    (page,) = finder.seen
    expected = page.copy()
    expected[BOX.top : BOX.bottom, BOX.left : BOX.right] = 0
    assert document == image_only_pdf(expected[np.newaxis], RENDER_DPI)
    # Nothing of the source document, its text or its document information
    # dictionary, is written; the claim and Burned In Annotation wait for
    # review.
    for sentinel in (PAGE_SENTINEL, AUTHOR_SENTINEL):
        assert sentinel.encode() not in result.data
    assert CODE not in _codes(written)
    assert written.BurnedInAnnotation == "YES"
    (material,) = [
        item for item in result.qc if type(item).__name__ == "RedactionMaterial"
    ]
    assert (material.frames, material.rows, material.columns) == (
        1,
        *page.shape[:2],
    )
    assert material.regions == ((0, (BOX,)),)
    assert material.decoded_sha256 == hashlib.sha256(page.tobytes()).digest()
    assert material.source is not None


def test_without_clean_pixel_data_a_document_is_still_sequestered():
    transform = InstanceTransform(
        policy.compose_custom_policy(()), KEY, unvalidated_policy=True
    )

    result = _transformed(transform, _encapsulated_pdf())

    assert isinstance(result, run.Sequestered)
    (sequestration,) = result.reasons
    assert (sequestration.path, sequestration.reason) == (
        DOCUMENT,
        SequesterReason.NO_DUMMY_VALUE,
    )


def test_a_pdf_without_a_document_claims_the_option():
    dataset = _encapsulated_pdf()
    del dataset.EncapsulatedDocument
    del dataset.EncapsulatedDocumentLength
    finder = Finder()

    result = _transformed(_transform(finder=finder), dataset)

    assert isinstance(result, run.Transformed)
    assert not finder.seen
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert _codes(written)[-1] == CODE
    assert written.BurnedInAnnotation == "NO"


def test_a_document_that_cannot_be_rendered_is_sequestered():
    dataset = _encapsulated_pdf()
    dataset.EncapsulatedDocument = _encrypted_pdf()

    result = _transformed(_transform(), dataset)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNCLEANABLE_DOCUMENT,)


def test_a_documents_content_sequence_still_sequesters_it_without_clean_structured_content():
    dataset = _encapsulated_pdf()
    item = pydicom.Dataset()
    item.RelationshipType = "CONTAINS"
    item.ValueType = "TEXT"
    item.TextValue = "INVENTED"
    dataset.ContentSequence = [item]

    result = _transformed(_transform(), dataset)

    assert isinstance(result, run.Sequestered)
    assert [reason.path.tag for reason in result.reasons] == ["(0040,A730)"]


def test_under_clean_recognizable_visual_features_a_document_is_held_for_its_pages():
    result = _transformed(
        _transform(
            (CLEAN_PIXEL_DATA, policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES),
            face_review=_corpus_run.NO_FACE_VERDICTS,
        ),
        _encapsulated_pdf(),
    )

    assert isinstance(result, run.Transformed)
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert HeldVisualFeatures(VisualFeaturesReason.DOCUMENT_PAGES) in held


def test_a_document_that_the_transform_leaves_pending_is_sequestered(monkeypatch):
    # Should the rendering not settle the document's D, the document is not
    # written as received.
    monkeypatch.setattr(instance_transform, "_with_document", lambda edits, _: edits)

    result = _transformed(_transform(), _encapsulated_pdf())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


def test_a_document_written_otherwise_than_planned_is_sequestered(monkeypatch):
    monkeypatch.setattr(instance_transform, "document_problem", lambda *_: True)

    result = _transformed(_transform(), _encapsulated_pdf())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.REDACTION_MISMATCH,)


# Two runs: review, then release.

_ACCEPTED, _REVISED, _REJECTED, _UNJUDGED = (
    "0-accepted.dcm",
    "1-revised.dcm",
    "2-rejected.dcm",
    "3-unjudged.dcm",
)
_PLAN = "4-plan.dcm"
_DOCUMENTS = (_ACCEPTED, _REVISED, _REJECTED, _UNJUDGED)


def _files():
    files = {}
    for number, name in enumerate(_DOCUMENTS):
        dataset = _encapsulated_pdf()
        dataset.SOPInstanceUID = f"2.25.99{number}1"
        dataset.InstanceNumber = number + 1
        files[name] = synthetic.written(dataset)
    files[_PLAN] = synthetic.written(synthetic.rt_plan())
    return files


def _write(directory, files):
    directory.mkdir()
    for name, data in files.items():
        (directory / name).write_bytes(data)


def _run(directory, source, transform):
    directory.mkdir()
    return run.run(
        run.discover(source),
        directory / "release",
        transform,
        ReleaseGate(),
        qc_destination=directory / "qc",
        reporter=transform.reporter,
    )


@contextlib.contextmanager
def _two_runs():
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        _write(directory / "source", _files())
        first = _run(directory / "first", directory / "source", _transform())
        pack = first.qc_pack.parent
        document = json.loads(first.qc_pack.read_text("utf-8"))
        positions = {
            Path(entry["source"]).name: entry["position"]
            for entry in document["instances"]
        }
        _attest(
            pack,
            (
                RedactionVerdict(positions[_ACCEPTED], Redaction.ACCEPTED),
                RedactionVerdict(
                    positions[_REVISED], Redaction.REVISED, ((0, (ADDED,)),)
                ),
                RedactionVerdict(positions[_REJECTED], Redaction.REJECTED),
            ),
        )
        finder = Finder(())
        second = _run(
            directory / "second",
            directory / "source",
            _transform(finder=finder, redaction_review=read_redaction_review(pack)),
        )
        entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
        outcomes = {
            Path(entry["source"]).name: (
                entry["disposition"],
                None
                if entry.get("output") is None
                else (directory / "second" / "release" / entry["output"]).read_bytes(),
            )
            for entry in entries
        }
        yield document, pack, outcomes, finder
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(name="two_runs", scope="module")
def fixture_two_runs():
    with _two_runs() as found:
        yield found


def test_the_first_run_holds_each_document_and_previews_each_page(two_runs):
    document, pack, _, _ = two_runs

    dispositions = {
        Path(entry["source"]).name: entry["disposition"]
        for entry in document["instances"]
    }
    assert dispositions == {
        **{name: "held-for-review" for name in _DOCUMENTS},
        _PLAN: "released",
    }
    redactions = document["redactions"]
    assert len(redactions) == len(_DOCUMENTS)
    for entry in redactions:
        assert entry["reason"] == "text-blacked-out"
        assert entry["frames"] == 1
        assert [region["boxes"] for region in entry["regions"]] == [
            [[BOX.top, BOX.left, BOX.bottom, BOX.right]]
        ]
        assert re.fullmatch("[0-9a-f]{64}", entry["decoded_sha256"])
        # Its SOP Class decides which pages the reviewer must be shown.
        assert entry["sop_class_uid"] == synthetic.ENCAPSULATED_PDF_STORAGE
    assert document["not_previewed"] == []
    for kind in ("redaction", "review-frame"):
        previewed = sorted(
            frame["position"]
            for preview in document["previews"]
            if preview["kind"] == kind
            for frame in preview["frames"]
        )
        assert previewed == sorted(entry["position"] for entry in redactions)
    for preview in document["previews"]:
        assert (pack / preview["file"]).read_bytes().startswith(b"\x89PNG")
    # Each page's review frame, which the review app draws over, is the page
    # as rendered from the source, since it has a region.
    rendered = rendered_pages(_encapsulated_pdf().EncapsulatedDocument)
    review_frames = [
        decoded_png((pack / preview["file"]).read_bytes())
        for preview in document["previews"]
        if preview["kind"] == "review-frame"
    ]
    assert len(review_frames) == len(_DOCUMENTS)
    for image in review_frames:
        np.testing.assert_array_equal(image, rendered[0])


@pytest.mark.parametrize("name, added", [(_ACCEPTED, ()), (_REVISED, (ADDED,))])
def test_an_approved_document_is_released_with_its_reviewed_regions(
    two_runs, name, added
):
    _, _, outcomes, finder = two_runs

    disposition, data = outcomes[name]

    assert disposition == "released"
    written = pydicom.dcmread(io.BytesIO(data))
    assert _codes(written)[-2:] == [markers.PROFILE_CODE, CODE]
    assert written.BurnedInAnnotation == "NO"
    rendered = rendered_pages(_encapsulated_pdf().EncapsulatedDocument)
    expected = rendered.copy()
    for box in (BOX, *added):
        expected[:, box.top : box.bottom, box.left : box.right] = 0
    assert bytes(written.EncapsulatedDocument) == image_only_pdf(expected, RENDER_DPI)
    for sentinel in (PAGE_SENTINEL, AUTHOR_SENTINEL):
        assert sentinel.encode() not in data
    # The finder never saw an approved document; it saw only the one
    # without a verdict.
    assert len(finder.seen) == 1


def test_a_rejected_document_is_sequestered(two_runs):
    _, _, outcomes, _ = two_runs

    assert outcomes[_REJECTED] == ("sequestered", None)


def test_a_document_without_a_verdict_is_held_again(two_runs):
    _, _, outcomes, _ = two_runs

    assert outcomes[_UNJUDGED][0] == "held-for-review"


def test_a_document_that_renders_otherwise_than_reviewed_is_held_again(
    tmp_path, monkeypatch
):
    _write(tmp_path / "source", {_ACCEPTED: _files()[_ACCEPTED]})
    first = _run(tmp_path / "first", tmp_path / "source", _transform())
    pack = first.qc_pack.parent
    (entry,) = json.loads(first.qc_pack.read_text("utf-8"))["instances"]
    _attest(pack, (RedactionVerdict(entry["position"], Redaction.ACCEPTED),))
    review = read_redaction_review(pack)
    # As where another build of PDFium renders the pages to other samples.
    rendered = encapsulated_documents.rendered_pages

    def otherwise(document):
        pages = rendered(document)
        pages[0, 0, 0] ^= 1
        return pages

    monkeypatch.setattr(document_cleaning, "rendered_pages", otherwise)
    finder = Finder()

    result = _transformed(
        _transform(finder=finder, redaction_review=review),
        pydicom.dcmread(io.BytesIO(_files()[_ACCEPTED])),
    )

    assert isinstance(result, run.Transformed)
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert held == (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),)
    assert len(finder.seen) == 1
