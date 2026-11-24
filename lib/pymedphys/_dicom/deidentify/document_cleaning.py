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

"""Clean an Encapsulated PDF's document as an image's frames are cleaned.

Table E.1-1 gives Encapsulated Document (0042,0011) D, and PS3.3 Table
C.24-2 treats the patient's identification and dates as text in the
document as burned-in annotation. Under the Clean Pixel Data Option, D is
met by a value that the engine makes from the document rather than a dummy
value (D-061): its pages, rendered to images
(:func:`.encapsulated_documents.rendered_pages`), with every region of text
that the text finder finds blacked out, written as an image-only PDF
(:func:`.image_pdf.image_only_pdf`). The rendered pages are the document's
frames, of one Rows and Columns, 8-bit RGB, so the QC pack lists their
regions, previews each page as written beside the page as rendered, and
records the SHA-256 of the rendered pages as it records that of compressed
Pixel Data's decoded frames (D-048).

Every such document is held for review, whether or not text was found, as
cleaned Pixel Data is (D-037). A later run given a reviewer's verdict on the
source file blacks out exactly the regions that the reviewer approved,
without the finder, on pages that render to the SHA-256 that the pack
records, and the instance claims the option; pages that render otherwise
are cleaned by the finder and held again (:class:`.pixel_cleaning.PixelsNotReviewed`).

Each region is set to black, zero in each sample, as for RGB Pixel Data.
What the document held beyond what its pages show, such as hidden text,
its document information dictionary, XMP metadata, attached files, and
scripts, is not written, since the image-only PDF holds only the pages'
samples. :func:`document_problem` checks the file written: its document
must be the image-only PDF planned, its Encapsulated Document Length that
PDF's length, and PDFium must read back from it, in the decoding child,
exactly the pages planned (:func:`.encapsulated_documents.written_pages`).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Sequence

from pymedphys._imports import numpy as np

from .encapsulated_documents import (
    ENCAPSULATED_DOCUMENT,
    ENCAPSULATED_DOCUMENT_LENGTH,
    RENDER_DPI,
    DocumentRefused,
    rendered_pages,
    written_pages,
)
from .image_pdf import image_only_pdf
from .pixel_cleaning import (
    FrameRegions,
    Layout,
    PixelDataRefused,
    PixelsNotReviewed,
    TextFinder,
    clipped_boxes,
)
from .reasons import PixelDataReason, TransformReason
from .source import SourceEvidence
from .text_detection import TextBox

# Black in each sample of an RGB page, as for RGB Pixel Data (D-037).
_FILL = (0, 0, 0)


def holds_document(source: SourceEvidence) -> bool:
    """Whether the source's top-level data set holds Encapsulated Document."""
    return ENCAPSULATED_DOCUMENT in source


@dataclasses.dataclass(frozen=True)
class DocumentRedaction:
    """What Clean Pixel Data did to an Encapsulated PDF's document.

    Attributes
    ----------
    layout : ~.pixel_cleaning.Layout
        Of the rendered pages, as frames: 8-bit RGB, the samples of each
        pixel together.
    regions : tuple of ~.pixel_cleaning.FrameRegions
        Each page with a region, by index from 0.
    value : bytes
        The image-only PDF of the pages with the regions blacked out, which
        is written as the document.
    decoded : bytes
        The rendered pages, as frames of ``layout``, which the QC pack shows
        as received and whose SHA-256 binds a reviewer's verdict (D-048).
    written : numpy.ndarray
        The pages with the regions blacked out, which ``value`` holds.
    """

    layout: Layout
    regions: tuple[FrameRegions, ...]
    value: bytes = dataclasses.field(repr=False)
    decoded: bytes = dataclasses.field(repr=False)
    written: np.ndarray = dataclasses.field(repr=False, compare=False)

    # As Redaction has them, so that the run's QC material and previews take
    # either.
    masks: tuple = ()
    overlays: int = 0
    rule_boxes: tuple[TextBox, ...] = ()

    @property
    def changed(self) -> bool:
        """Always true: the document is written as its rendering, region or not."""
        return True

    @property
    def decoded_sha256(self) -> bytes:
        """The SHA-256 of the rendered pages."""
        return hashlib.sha256(self.decoded).digest()

    @property
    def reason(self) -> PixelDataReason:
        """Why the instance is held for review."""
        if self.regions:
            return PixelDataReason.TEXT_BLACKED_OUT
        return PixelDataReason.NO_TEXT_FOUND


def clean_document(
    source: SourceEvidence,
    finder: TextFinder | None,
    *,
    reviewed: Sequence[tuple[int, Sequence[TextBox]]] | None = None,
    decoded_sha256: bytes | None = None,
) -> DocumentRedaction:
    """Return the instance's document rendered, with regions blacked out.

    Parameters
    ----------
    source : SourceEvidence
        An instance that holds Encapsulated Document (0042,0011).
    finder : TextFinder or None
        Searches each rendered page, where no review is given; its regions
        are clipped to the page, as a frame's are.
    reviewed : sequence of (int, sequence of TextBox), optional
        A reviewer's regions, by page index from 0, which are blacked out
        in place of the finder's, each never clipped.
    decoded_sha256 : bytes, optional
        With ``reviewed``, the SHA-256 of the rendered pages that the
        reviewed QC pack records, which the pages rendered now must have.

    Raises
    ------
    PixelDataRefused
        With the reason of :class:`.encapsulated_documents.DocumentRefused`
        where the document cannot be rendered, and with
        :attr:`~.reasons.TransformReason.REDACTION_MISMATCH` where a
        reviewed region lies on a page that the document does not have, or
        goes past its page.
    PixelsNotReviewed
        Where ``reviewed`` is given and the pages render to another SHA-256
        than ``decoded_sha256``, or none is given, before any region is
        applied.
    TypeError
        If the finder gives anything but TextBox objects, or neither a
        finder nor a review is given.
    """
    if finder is None and reviewed is None:
        raise TypeError("a document is cleaned by a text finder or a review")
    try:
        pages = rendered_pages(source.value_field(ENCAPSULATED_DOCUMENT))
    except DocumentRefused as refused:
        raise PixelDataRefused(refused.reason) from None
    count, rows, columns = pages.shape[:3]
    decoded = pages.tobytes()
    by_page = {} if reviewed is None else {i: tuple(b) for i, b in reviewed}
    if reviewed is not None:
        if decoded_sha256 != hashlib.sha256(decoded).digest():
            raise PixelsNotReviewed()
        if any(not 0 <= index < count for index in by_page) or any(
            box.bottom > rows or box.right > columns
            for boxes in by_page.values()
            for box in boxes
        ):
            raise PixelDataRefused(TransformReason.REDACTION_MISMATCH)
    written = pages.copy()
    regions = []
    for index in range(count):
        if reviewed is not None:
            boxes = by_page.get(index, ())
        else:
            assert finder is not None
            boxes = clipped_boxes(finder.find(pages[index]), rows, columns)
        boxes = tuple(sorted(set(boxes)))
        if not boxes:
            continue
        for box in boxes:
            written[index, box.top : box.bottom, box.left : box.right] = _FILL
        regions.append(FrameRegions(index, boxes, _FILL))
    layout = Layout(count, rows, columns, 3, 8, 8, False, "RGB", False)
    return DocumentRedaction(
        layout,
        tuple(regions),
        image_only_pdf(written, RENDER_DPI),
        decoded,
        written,
    )


def document_problem(output: SourceEvidence, redaction: DocumentRedaction) -> bool:
    """Whether the file written holds other than the document planned.

    Its Encapsulated Document must be the image-only PDF planned, with no
    padding, since that PDF is of even length; its Encapsulated Document
    Length, where present, that PDF's length; and PDFium must read back,
    from that PDF, exactly the pages planned
    (:func:`.encapsulated_documents.written_pages`).
    """
    if not holds_document(output):
        return True
    if output.value_field(ENCAPSULATED_DOCUMENT) != redaction.value:
        return True
    if ENCAPSULATED_DOCUMENT_LENGTH in output:
        length = output.dataset().get((0x0042, 0x0015))
        if length is None or length.value != len(redaction.value):
            return True
    layout = redaction.layout
    try:
        read = written_pages(
            redaction.value, layout.frames, layout.rows, layout.columns
        )
    except DocumentRefused:
        return True
    return not np.array_equal(read, redaction.written)
