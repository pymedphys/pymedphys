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

"""Write an image-only PDF: one page per image, and nothing else.

Under the Clean Pixel Data Option, an Encapsulated PDF's document is
released only as the pages that a reviewer saw, rendered to images and with
the approved regions blacked out (D-061). :func:`image_only_pdf` writes
those pages as a PDF 1.4 document (ISO 32000-1 is PDF 1.7; PDF 1.4 is its
subset that every reader opens) in which each page holds one image and a
content stream that draws it to fill the page, and nothing else: no text,
fonts, document information dictionary, XMP metadata, file identifier,
outline, annotations, form fields, attached files, actions, or JavaScript.
What the source document held beyond what its pages showed, such as hidden
text, metadata, or attachments, is therefore not written.

Each image is 8-bit DeviceRGB, compressed with FlateDecode, which is
lossless, so a reader decodes the samples written exactly; ``/Interpolate``
is false, so that a reader shows each sample as a square rather than
smoothing it. Each page is as many points wide and high as its image has
pixels at the resolution given, so the page prints at the size it was
rendered from.

The output is a function of the pages and the resolution alone: objects in
a fixed order and form, offsets counted, and the samples compressed by
:func:`zlib.compress` at level 9. A different build of zlib may compress
them to different bytes, which decode to the same samples.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence

from pymedphys._imports import numpy as np

# Two bytes above 127 after the header, so that a tool that guesses whether
# a file is text treats it as binary (ISO 32000-1 Section 7.5.2).
_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_COMPRESSION_LEVEL = 9
# Points per inch (ISO 32000-1 Section 8.3.2.3).
_POINTS_PER_INCH = 72


class ImagePdfError(ValueError):
    """Pages that cannot be written as an image-only PDF."""


def image_only_pdf(pages: Sequence[np.ndarray] | np.ndarray, dpi: int) -> bytes:
    """Return a PDF whose pages are ``pages``, one image each, and nothing else.

    Parameters
    ----------
    pages : sequence of numpy.ndarray, or numpy.ndarray
        Each page as 8-bit RGB samples, rows by columns by 3, from the top
        row down, or all of them as one array, pages by rows by columns by
        3.
    dpi : int
        The resolution, in pixels per inch, at which a page's image fills
        it. 72 must be a whole multiple of ``dpi`` divided by the greatest
        common divisor of the two, so that each page's size in points has at
        most two decimal places; 72, 100, 144, 150, 200, 300, and 600 do.

    Returns
    -------
    bytes
        The document, of even length, so that it fills a DICOM value of VR
        OB without padding.

    Raises
    ------
    ImagePdfError
        If there is no page, a page is not 8-bit RGB of at least one row and
        one column, or ``dpi`` does not give sizes of at most two decimal
        places.
    """
    if not isinstance(dpi, int) or isinstance(dpi, bool) or dpi < 1:
        raise ImagePdfError("the resolution must be a whole number above 0")
    if (100 * _POINTS_PER_INCH) % dpi:
        raise ImagePdfError("the resolution gives page sizes of more than two places")
    if len(pages) == 0:
        raise ImagePdfError("an image-only PDF needs at least one page")
    objects: list[bytes] = []
    count = len(pages)
    # Objects 1 and 2 are the catalogue and the page tree; each page then
    # takes three: the page, its content stream, and its image.
    kids = b" ".join(b"%d 0 R" % (3 + 3 * index) for index in range(count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, count))
    for index, page in enumerate(pages):
        samples = _samples(page)
        rows, columns = samples.shape[:2]
        width, height = _points(columns, dpi), _points(rows, dpi)
        number = 3 + 3 * index
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
            b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
            % (width, height, number + 2, number + 1)
        )
        # The image's unit square, scaled to the page (Section 8.3.4).
        drawn = b"q %s 0 0 %s 0 0 cm /Im0 Do Q\n" % (width, height)
        objects.append(_stream(b"", drawn))
        compressed = zlib.compress(samples.tobytes(), _COMPRESSION_LEVEL)
        objects.append(
            _stream(
                b"/Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 "
                b"/Interpolate false /Filter /FlateDecode " % (columns, rows),
                compressed,
            )
        )
    return _document(objects)


def _samples(page: object) -> np.ndarray:
    """Return a page's samples, C-ordered, or refuse a page of another form."""
    if not isinstance(page, np.ndarray) or page.dtype != np.uint8:
        raise ImagePdfError("each page must be an array of 8-bit samples")
    if page.ndim != 3 or page.shape[2] != 3 or page.shape[0] < 1 or page.shape[1] < 1:
        raise ImagePdfError("each page must be rows by columns of RGB samples")
    return np.ascontiguousarray(page)


def _points(pixels: int, dpi: int) -> bytes:
    """Return a length in pixels at ``dpi`` as points, exactly, to at most
    two decimal places, without a float."""
    hundredths = pixels * 100 * _POINTS_PER_INCH // dpi
    whole, part = divmod(hundredths, 100)
    if not part:
        return b"%d" % whole
    return (b"%d.%02d" % (whole, part)).rstrip(b"0")


def _stream(dictionary: bytes, data: bytes) -> bytes:
    """Return a stream object's body: its dictionary, with its length, and data."""
    return b"<< %s/Length %d >>\nstream\n%s\nendstream" % (
        dictionary,
        len(data),
        data,
    )


def _document(objects: list[bytes]) -> bytes:
    """Return the file: the header, each object numbered from 1, the
    cross-reference table, and a trailer that names only the catalogue."""
    parts = [_HEADER]
    offset = len(_HEADER)
    offsets = []
    for number, body in enumerate(objects, start=1):
        written = b"%d 0 obj\n%s\nendobj\n" % (number, body)
        offsets.append(offset)
        parts.append(written)
        offset += len(written)
    # Each entry is exactly 20 bytes, its end of line two (Section 7.5.4).
    table = [b"xref\n0 %d\n" % (len(objects) + 1), b"0000000000 65535 f\r\n"]
    table.extend(b"%010d 00000 n\r\n" % position for position in offsets)
    parts.extend(table)
    parts.append(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, offset)
    )
    document = b"".join(parts)
    # A DICOM value of VR OB has even length; an end of line after the
    # end-of-file marker, which readers ignore, makes it so.
    if len(document) % 2:
        document += b"\n"
    return document
