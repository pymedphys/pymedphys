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

"""Decode a sequence's items, once they are shown to fill its value.

pydicom decodes some malformed values of VR SQ without an error: it accepts
an item whose length runs past the value, and an element where an item
belongs, and leaves out what they hold. :func:`decode_items` has pydicom
decode a value only once :func:`.file_layout.reads_as_items` finds that it
holds only items. The element decoder (:mod:`.elements`), the first pass's
reference records (:mod:`.references`), and the removal of private
attributes (:mod:`.private_attributes`) pass each sequence value that
pydicom holds undecoded through it before they read its items, and each
reports :class:`UnreadableItems` with its own exception, by the path of the
sequence. pydicom's warnings and log records while it decodes are redacted
by :func:`.diagnostics.redacted_diagnostics`, whether or not the caller
redacts them too.
"""

from __future__ import annotations

from collections.abc import Sequence

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import reads_as_items


class UnreadableItems(Exception):
    """A sequence's value that does not hold only items, or does not decode.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident. Its message never quotes the value, and pydicom's
    exception, whose message can, is replaced rather than chained.
    """

    def __init__(self) -> None:
        super().__init__("the value is not a sequence's items")


def decode_items(
    value: bytes,
    *,
    explicit: bool,
    codecs: Sequence[str] = (),
    little_endian: bool = True,
    offset: int = 0,
    nested: bool = True,
) -> pydicom.Sequence:
    """Return the items of a sequence's encoded value, as pydicom decodes them.

    Parameters
    ----------
    value : bytes
        The value of an element of VR SQ, without its header. An empty value
        has no items.
    explicit : bool
        Whether the items are in explicit VR. Those in a value of VR UN are
        not, whatever the transfer syntax (PS3.5 Section 6.2.2).
    codecs : sequence of str
        The codecs, as pydicom names them, of the data set that holds the
        sequence, which apply to each item without its own Specific
        Character Set (0008,0005) (PS3.5 Section 7.5.3). Empty gives
        pydicom's default, ISO 8859-1, which reads the Default Character
        Repertoire as it is but does not refuse other bytes.
    little_endian : bool
        Whether the value is little endian. Only a little endian value can
        be read as items, so a big endian one is refused.
    offset : int
        Where in its file the value starts, which pydicom records for each
        element of the items.
    nested : bool
        Whether a sequence of defined length nested in the items must hold
        only items too. pydicom decodes such a sequence only when it is
        accessed, so a caller that decodes each through this function as it
        reaches it can leave it, and refuse it by its own path. A sequence of
        undefined length, which pydicom decodes with the value, is read
        either way. Items nested more than :data:`.file_layout.MAX_NESTING`
        deep in what is read are refused, counting from this value, not from
        the top level of its data set.

    Raises
    ------
    UnreadableItems
        If the value does not hold only items, as
        :func:`.file_layout.reads_as_items` reads them, or pydicom cannot
        decode them. Both give the same message, and neither its cause nor
        its context holds pydicom's exception.

    Examples
    --------
    >>> item = b"\\x08\\x00\\x55\\x11\\x06\\x00\\x00\\x002.25.1"
    >>> value = b"\\xfe\\xff\\x00\\xe0\\x0e\\x00\\x00\\x00" + item
    >>> (decoded,) = decode_items(value, explicit=False)
    >>> decoded.ReferencedSOPInstanceUID
    '2.25.1'

    Without its last two bytes, the item runs past the value:

    >>> decode_items(value[:-2], explicit=False)  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    UnreadableItems: the value is not a sequence's items
    """
    if not value:
        return pydicom.Sequence()
    decoded = None
    if little_endian and reads_as_items(value, explicit=explicit, nested=nested):
        try:
            with redacted_diagnostics():
                decoded = pydicom.values.convert_SQ(
                    value, not explicit, True, list(codecs) or None, offset
                )
        # pydicom raises many types for a value it cannot decode, and its
        # message can quote the value, so it is raised from neither here.
        except Exception:  # pylint: disable = broad-exception-caught
            pass
    if decoded is None:
        raise UnreadableItems()
    return decoded
