"""Read lossless JPEG files, such as those that Elekta iView writes.

A file holds one codestream of ITU-T T.81 Process 14 (SOF3), which GDCM
decodes through pydicom's decoder for JPEG Lossless, since pylibjpeg-libjpeg
is licensed under the GNU GPL.
"""

import pathlib
import struct

from pymedphys._imports import imageio, pydicom
from pymedphys._imports import numpy as np

_JPEG_LOSSLESS = "1.2.840.10008.1.2.4.57"
_SOI = b"\xff\xd8"
_SOF3 = 0xFFC3
# The frame header markers of the other coding processes (T.81 Table B.1).
_OTHER_FRAMES = frozenset(
    {0xFFC0, 0xFFC1, 0xFFC2, 0xFFC5, 0xFFC6, 0xFFC7}
    | {0xFFC9, 0xFFCA, 0xFFCB, 0xFFCD, 0xFFCE, 0xFFCF}
)
_EIGHT_BITS = 8
_COLOUR = 3


def _frame_header(data: bytes) -> tuple[int, int, int, int]:
    """Return the precision, rows, columns, and components of a lossless
    JPEG codestream's frame header."""
    if not data.startswith(_SOI):
        raise ValueError("the file is not a JPEG codestream")
    position = len(_SOI)
    while True:
        # Any number of 0xFF fill bytes may precede a marker (T.81 B.1.1.2).
        while data[position : position + 2] == b"\xff\xff":
            position += 1
        if position + 4 > len(data):
            break
        marker, length = struct.unpack_from(">HH", data, position)
        if marker == _SOF3:
            return struct.unpack_from(">BHHB", data, position + 4)
        if marker in _OTHER_FRAMES:
            raise ValueError("the file is not a lossless JPEG (Process 14)")
        position += 2 + length
    raise ValueError("the file's JPEG codestream has no frame header")


def imread(input_filepath) -> "np.ndarray":
    with open(input_filepath, "rb") as f:
        data = f.read()

    precision, rows, columns, components = _frame_header(data)
    decoder = pydicom.pixels.get_decoder(_JPEG_LOSSLESS)
    # pydicom decodes encapsulated Pixel Data: an empty Basic Offset Table
    # and one fragment.
    im, _ = decoder.as_array(
        pydicom.encaps.encapsulate([data]),
        decoding_plugin="gdcm",
        rows=rows,
        columns=columns,
        samples_per_pixel=components,
        bits_allocated=_EIGHT_BITS if precision <= _EIGHT_BITS else 16,
        bits_stored=precision,
        pixel_representation=0,
        photometric_interpretation="RGB" if components == _COLOUR else "MONOCHROME2",
        number_of_frames=1,
        planar_configuration=0,
    )

    return im


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.tif")

    im = imread(input_filepath)
    imageio.imwrite(str(output_filepath), im, format=".tif")
