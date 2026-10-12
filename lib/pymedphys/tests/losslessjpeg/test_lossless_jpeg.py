import pathlib
import tempfile

import pytest

from pymedphys._imports import imageio
from pymedphys._imports import numpy as np

import pymedphys
import pymedphys._losslessjpeg

from ..dicom import _synthetic_compressed as compressed


def test_lossless_jpeg():
    testing_data = pymedphys.zip_data_paths("lossless_jpeg_test.zip")

    input_jpg = [path for path in testing_data if path.name == "input.jpg"][0]
    output_ppm = [path for path in testing_data if path.name == "output.ppm"][0]

    reference = imageio.imread(output_ppm)

    with tempfile.TemporaryDirectory() as tmpdirname:
        output_file = pathlib.Path(tmpdirname).joinpath("output.ppm")
        pymedphys._losslessjpeg.convert_lossless_jpeg(  # pylint: disable = protected-access
            input_jpg, output_file
        )

        result = imageio.imread(output_file)

    assert np.all(reference == result)


@pytest.mark.parametrize("fill", [0, 1, 2, 3, 8])
def test_marker_fill_bytes_before_the_frame_header_are_skipped(tmp_path, fill):
    frame = np.array([[128, 3, 250], [0, 255, 17]], dtype=np.uint8)
    codestream = compressed.jpeg_lossless(frame, precision=8)
    frame_header = codestream.index(b"\xff\xc3")
    path = tmp_path / "input.jpg"
    path.write_bytes(
        codestream[:frame_header] + b"\xff" * fill + codestream[frame_header:]
    )

    result = pymedphys._losslessjpeg.imread(  # pylint: disable = protected-access
        path
    )

    assert np.array_equal(result, frame)
