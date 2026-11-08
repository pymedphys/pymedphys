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

"""Render an Encapsulated PDF's pages, and read back the image-only PDF
written in its place, in the decoding child.

Under the Clean Pixel Data Option, an Encapsulated PDF's document,
Encapsulated Document (0042,0011), is released only as an image-only PDF
of its pages as a reviewer saw them, with the regions that the reviewer
approved blacked out (D-061). PS3.3 Table C.24-2 treats the patient's
identification and dates as text in the document as burned-in annotation,
so the document's rendered pages are cleaned and reviewed as an image's
frames are (D-037, D-048).

:func:`rendered_pages` renders each page with PDFium, through pypdfium2, at
:data:`RENDER_DPI`, to 8-bit RGB on white, with the annotations that a
viewer draws, and with the saved appearances of its AcroForm fields, such
as a filled-in text field's value and a ticked check box. Those fields are
widget annotations, which PDFium draws only through a form-filling
environment (``FPDF_FFLDraw``, fpdf_formfill.h), so one is started for a
document with an AcroForm; its document and page actions are never run,
and the pypdfium2 wheels are built without V8 or XFA, so no script in the
document can run. PDFium parses the document, a format of many parts that
a crafted file can exploit, so it runs in the decoding child
(:func:`.isolated_decoding.run`), as GDCM and OpenJPEG do, and what the
child sends back is checked against the sizes it gave before any page is
rendered.

A page is rendered at its physical size: :data:`RENDER_DPI` pixels to the
inch of the page as printed, which is its size in default user space units,
1/72 inch each, multiplied by its UserUnit (ISO 32000-1 Table 30). PDFium
ignores UserUnit, which it does not expose, so the child reads it from the
page as PDFium writes it alone into a new document, where every name is
written without escapes and no object is in an object stream. Pages of
different sizes are padded with white, at their right and bottom, to the
largest width and height, so that every page is a frame of one Rows and
Columns, as a QC pack records them.

A document is refused, with
:attr:`~.reasons.TransformReason.UNCLEANABLE_DOCUMENT`, where it is
encrypted, which includes one that opens without a password but restricts
what may be done with it, holds an XFA form, whose content PDFium cannot
draw without XFA, gives a page a UserUnit that is not one positive number,
has no page or more than :data:`MAX_PAGES`,
holds more than :data:`MAX_DOCUMENT_BYTES`, or a page larger than
:data:`MAX_PAGE_PIXELS` once rendered, would need more than
:data:`MAX_RENDERED_BYTES` once its pages are padded, or cannot be opened or
rendered; and with :attr:`~.reasons.TransformReason.NO_RENDERER` where
pypdfium2 is not installed or the child cannot be run.

:func:`written_pages` reads back the image-only PDF that
:func:`.image_pdf.image_only_pdf` wrote, in the child, independently of the
writer, and returns its pages' samples only where it has the pages
expected and each holds one 8-bit DeviceRGB image, compressed with
FlateDecode alone, of the page's size in pixels, and nothing else: no text
object or character, annotation, form, or attached file. A written document is
released only where those samples are the pages that the reviewer approved
(:func:`.document_cleaning.document_problem`).
"""

from __future__ import annotations

import base64
import binascii
import importlib.util
import io
import math
import re
from collections.abc import Collection

from pymedphys._imports import numpy as np

from . import isolated_decoding
from .file_layout import ElementPath
from .policy import CLEAN_PIXEL_DATA
from .reasons import TransformReason

ENCAPSULATED_PDF = "Encapsulated PDF"
ENCAPSULATED_DOCUMENT = ElementPath((), "(0042,0011)")
ENCAPSULATED_DOCUMENT_LENGTH = ElementPath((), "(0042,0015)")

# The resolution at which pages are rendered and written, in pixels per inch:
# 10-point text is about 21 pixels high, which the text detector finds and a
# reviewer reads, and an A4 page is 1240 by 1754 pixels, 6.5 MB as RGB.
RENDER_DPI = 150
# The largest document that is rendered, in bytes.
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
# The most pages that a document may have.
MAX_PAGES = 200
# The most pixels that a page may have once rendered: an A2 page at
# RENDER_DPI has 17.4 million.
MAX_PAGE_PIXELS = 24_000_000
# The most bytes that a document's rendered pages may fill once padded.
MAX_RENDERED_BYTES = 768 * 1024 * 1024
# The white that pages are rendered on and padded with.
_WHITE = 255
# Points per inch (ISO 32000-1 Section 8.3.2.3).
_POINTS_PER_INCH = 72
# Pixels per point, a little less than the quotient, so that a page whose
# size at RENDER_DPI is a whole number of pixels, such as US Letter's 1275 by
# 1650, renders to that number rather than one more, where the quotient's
# rounding error would carry its product just past it; pypdfium2 rounds a
# page's size up to whole pixels. The page is drawn smaller by a part in a
# trillion, which no pixel shows.
_SCALE = RENDER_DPI / _POINTS_PER_INCH * (1 - 2**-40)
# A UserUnit key, and one with its value a number (ISO 32000-1 Sections
# 7.3.3 and 7.3.5), as PDFium writes them: names without escapes, and a
# number's digits followed by white space or a delimiter. A UserUnit that
# is anything else, such as an indirect reference, refuses the document.
_USER_UNIT = re.compile(rb"/UserUnit(?![^\x00\t\n\x0c\r ()<>\[\]{}/%])")
_USER_UNIT_NUMBER = re.compile(
    rb"/UserUnit[\x00\t\n\x0c\r ]*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))"
    rb"(?=[\x00\t\n\x0c\r ]*[/>])"
)


class DocumentRefused(Exception):
    """A document that cannot be rendered or read back, with a value-free reason."""

    def __init__(self, reason: TransformReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def releases_document(options: Collection[str], iod: str) -> bool:
    """Whether a policy with ``options`` releases a document of ``iod`` as
    its reviewed rendering: an Encapsulated PDF under Clean Pixel Data
    (D-061)."""
    return CLEAN_PIXEL_DATA in options and iod == ENCAPSULATED_PDF


def renderer_available() -> bool:
    """Whether pypdfium2 is installed, so that the child can render."""
    return importlib.util.find_spec("pypdfium2") is not None


def rendered_pages(document: bytes) -> np.ndarray:
    """Return a PDF's pages rendered at :data:`RENDER_DPI`, padded to one size.

    Parameters
    ----------
    document : bytes
        The PDF, as Encapsulated Document (0042,0011) holds it, with any
        byte of padding after it, which PDFium ignores.

    Returns
    -------
    numpy.ndarray
        Of uint8, pages by rows by columns by 3, RGB, each page padded with
        white at its right and bottom to the largest page's rows and
        columns.

    Raises
    ------
    DocumentRefused
        As the module describes.
    """
    if not isinstance(document, bytes) or len(document) > MAX_DOCUMENT_BYTES:
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
    if not renderer_available():
        raise DocumentRefused(TransformReason.NO_RENDERER)
    sizes = _checked_sizes(_in_child(_page_sizes, document))
    rows = max(size[0] for size in sizes)
    columns = max(size[1] for size in sizes)
    if len(sizes) * rows * columns * 3 > MAX_RENDERED_BYTES:
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
    pages = np.full((len(sizes), rows, columns, 3), _WHITE, dtype=np.uint8)
    for index, (page_rows, page_columns) in enumerate(sizes):
        size = page_rows * page_columns * 3
        sent = _in_child(
            _page_rendered,
            document,
            index,
            page_rows,
            page_columns,
            result_bytes=_base64_size(size),
        )
        pages[index, :page_rows, :page_columns] = np.frombuffer(
            _samples(sent, size), dtype=np.uint8
        ).reshape(page_rows, page_columns, 3)
    return pages


def written_pages(document: bytes, pages: int, rows: int, columns: int) -> np.ndarray:
    """Return the samples of an image-only PDF's pages, read back by PDFium.

    Parameters
    ----------
    document : bytes
        The PDF that :func:`.image_pdf.image_only_pdf` wrote.
    pages, rows, columns : int
        How many pages it must have, and the rows and columns of each
        page's image.

    Returns
    -------
    numpy.ndarray
        Of uint8, pages by rows by columns by 3, RGB.

    Raises
    ------
    DocumentRefused
        With :attr:`~.reasons.TransformReason.REDACTION_MISMATCH` where the
        document does not have that form, as the module describes, or with
        :attr:`~.reasons.TransformReason.NO_RENDERER` where the child cannot
        read it.
    """
    if not renderer_available():
        raise DocumentRefused(TransformReason.NO_RENDERER)
    size = rows * columns * 3
    read = np.empty((pages, rows, columns, 3), dtype=np.uint8)
    try:
        counted = _in_child(_image_only_pages, document)
        if counted != pages:
            raise DocumentRefused(TransformReason.REDACTION_MISMATCH)
        for index in range(pages):
            sent = _in_child(
                _image_only_page,
                document,
                index,
                rows,
                columns,
                result_bytes=_base64_size(size),
            )
            read[index] = np.frombuffer(_samples(sent, size), dtype=np.uint8).reshape(
                rows, columns, 3
            )
    except DocumentRefused as refused:
        if refused.reason is TransformReason.NO_RENDERER:
            raise
        raise DocumentRefused(TransformReason.REDACTION_MISMATCH) from None
    return read


def _in_child(task, *args, result_bytes: int = 0):
    """Return ``task(*args)`` from the decoding child, refusing the document
    where the call fails, or where the child cannot be run."""
    try:
        return isolated_decoding.run(task, *args, result_bytes=result_bytes)
    except isolated_decoding.DecoderUnavailable:
        raise DocumentRefused(TransformReason.NO_RENDERER) from None
    except isolated_decoding.DecodingFailed:
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT) from None


def _base64_size(size: int) -> int:
    """The length of ``size`` bytes once encoded as base64."""
    return 4 * -(-size // 3)


def _checked_sizes(sent: object) -> list[tuple[int, int]]:
    """Return the rows and columns of each page that :func:`_page_sizes`
    sent, or refuse the document.

    ``sent`` may come from a child that the document subverted, so it is
    only compared with what is allowed, never used to find a type or name.
    """
    if not isinstance(sent, list) or not 1 <= len(sent) <= MAX_PAGES:
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
    sizes = []
    for size in sent:
        if not (
            isinstance(size, list)
            and len(size) == 2
            and all(_is_count(value) for value in size)
            and size[0] * size[1] <= MAX_PAGE_PIXELS
        ):
            raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
        sizes.append((size[0], size[1]))
    return sizes


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _samples(sent: object, size: int) -> bytes:
    """Return the samples that the child sent as base64 text, or refuse them
    where they are not text of exactly ``size`` bytes."""
    if not isinstance(sent, str):
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
    try:
        samples = base64.b64decode(sent.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error):
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT) from None
    if len(samples) != size:
        raise DocumentRefused(TransformReason.UNCLEANABLE_DOCUMENT)
    return samples


# What follows runs in the decoding child.


def _opened(document: bytes):
    """Return the document opened by PDFium, with a form-filling environment
    where it has an AcroForm, refusing an encrypted one or an XFA form.

    The environment is started before any page is loaded, as pypdfium2
    requires for its fields to be drawn. No document action is run: pypdfium2
    runs none unless asked, and the build has no JavaScript engine.

    Raises
    ------
    ValueError
        If the document is encrypted or holds an XFA form, which the child
        returns only as a failure.
    """
    from pymedphys._imports import pypdfium2  # pylint: disable = import-outside-toplevel

    raw = pypdfium2.raw
    pdf = pypdfium2.PdfDocument(document)
    try:
        # -1 where the document has no security handler, that is, is not
        # encrypted (fpdf_doc.h).
        if raw.FPDF_GetSecurityHandlerRevision(pdf) != -1:
            raise ValueError("encrypted")
        if pdf.get_formtype() not in (raw.FORMTYPE_NONE, raw.FORMTYPE_ACRO_FORM):
            raise ValueError("xfa")
        pdf.init_forms()
    except BaseException:
        pdf.close()
        raise
    return pdf


def _saved(pdf) -> bytes:
    """The document as PDFium writes it whole, not as an update."""
    from pymedphys._imports import pypdfium2  # pylint: disable = import-outside-toplevel

    buffer = io.BytesIO()
    pdf.save(buffer, flags=pypdfium2.raw.FPDF_NO_INCREMENTAL)
    return buffer.getvalue()


def _user_unit(pdf, index: int) -> float:
    """The page's UserUnit, 1 where it has none.

    The page is written alone into a new document, so that only its own
    dictionary, and the resources and annotations it uses, can hold the key.
    Each UserUnit found must be the same positive, finite number.

    Raises
    ------
    ValueError
        If a UserUnit is anything else.
    """
    from pymedphys._imports import pypdfium2  # pylint: disable = import-outside-toplevel

    alone = pypdfium2.PdfDocument.new()
    try:
        # Raises where PDFium cannot import the page.
        alone.import_pages(pdf, [index])
        saved = _saved(alone)
    finally:
        alone.close()
    keys = _USER_UNIT.findall(saved)
    if not keys:
        return 1.0
    numbers = _USER_UNIT_NUMBER.findall(saved)
    units = {float(number) for number in numbers}
    if len(numbers) != len(keys) or len(units) != 1:
        raise ValueError("user unit")
    (unit,) = units
    if not (math.isfinite(unit) and unit > 0):
        raise ValueError("user unit")
    return unit


def _rendered_size(page, unit: float) -> tuple[int, int]:
    """The rows and columns of a page of UserUnit ``unit`` once rendered at
    :data:`RENDER_DPI`, as :meth:`pypdfium2.PdfPage.render` sizes its bitmap
    at scale ``_SCALE * unit``."""
    return (
        math.ceil(page.get_height() * (_SCALE * unit)),
        math.ceil(page.get_width() * (_SCALE * unit)),
    )


def _page_sizes(document: bytes) -> list[list[int]]:
    """Return the rows and columns of each page once rendered.

    A document with more than :data:`MAX_PAGES` pages fails, so that its
    pages are not counted out.
    """
    pdf = _opened(document)
    try:
        if not 1 <= len(pdf) <= MAX_PAGES:
            raise ValueError("pages")
        sizes = []
        count = len(pdf)
        for index in range(count):
            unit = _user_unit(pdf, index)
            page = pdf[index]
            try:
                sizes.append(list(_rendered_size(page, unit)))
            finally:
                page.close()
        return sizes
    finally:
        pdf.close()


def _page_rendered(document: bytes, index: int, rows: int, columns: int) -> str:
    """Return one page rendered at :data:`RENDER_DPI` as 8-bit RGB on white,
    as base64 text, rows by columns by 3, in C order.

    The page must render to ``rows`` and ``columns``, as
    :func:`_page_sizes` gave them, so that a page is never rendered larger
    than was checked.
    """
    pdf = _opened(document)
    try:
        unit = _user_unit(pdf, index)
        page = pdf[index]
        try:
            if _rendered_size(page, unit) != (rows, columns):
                raise ValueError("size")
            # Annotations are drawn as a viewer draws them, and the fields
            # of an AcroForm, which are not, through its environment.
            bitmap = page.render(
                scale=_SCALE * unit,
                may_draw_forms=True,
                draw_annots=True,
                rev_byteorder=True,
                fill_color=(_WHITE, _WHITE, _WHITE, _WHITE),
            )
            try:
                samples = np.asarray(bitmap.to_numpy())
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        pdf.close()
    if samples.shape != (rows, columns, 3) or samples.dtype != np.uint8:
        raise ValueError("bitmap")
    return base64.b64encode(np.ascontiguousarray(samples).tobytes()).decode("ascii")


def _image_only_pages(document: bytes) -> int:
    """Return how many pages an image-only PDF has, once checked to attach
    no file and hold no form."""
    pdf = _opened(document)
    try:
        if pdf.count_attachments():
            raise ValueError("attachments")
        if pdf.formenv is not None:
            raise ValueError("form")
        return len(pdf)
    finally:
        pdf.close()


def _image_only_page(document: bytes, index: int, rows: int, columns: int) -> str:
    """Return the samples of the one image on a page of an image-only PDF,
    as base64 text, rows by columns by 3, in C order.

    The page must hold exactly one page object, an 8-bit DeviceRGB image of
    ``columns`` by ``rows`` pixels compressed with FlateDecode alone, and
    no character or annotation.
    """
    from pymedphys._imports import pypdfium2  # pylint: disable = import-outside-toplevel

    raw = pypdfium2.raw
    pdf = _opened(document)
    try:
        page = pdf[index]
        try:
            if raw.FPDFPage_GetAnnotCount(page) != 0:
                raise ValueError("annotations")
            text = page.get_textpage()
            try:
                if text.count_chars() != 0:
                    raise ValueError("text")
            finally:
                text.close()
            objects = list(page.get_objects(max_depth=1))
            if len(objects) != 1 or objects[0].type != raw.FPDF_PAGEOBJ_IMAGE:
                raise ValueError("objects")
            (image,) = objects
            metadata = image.get_metadata()
            if (
                (metadata.width, metadata.height) != (columns, rows)
                or metadata.bits_per_pixel != 24
                or metadata.colorspace != raw.FPDF_COLORSPACE_DEVICERGB
                or image.get_filters() != ["FlateDecode"]
            ):
                raise ValueError("image")
            data = bytes(image.get_data(decode_simple=True))
        finally:
            page.close()
    finally:
        pdf.close()
    if len(data) != rows * columns * 3:
        raise ValueError("samples")
    return base64.b64encode(data).decode("ascii")
