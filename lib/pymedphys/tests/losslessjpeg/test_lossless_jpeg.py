import pathlib
import tempfile

from pymedphys._imports import imageio
from pymedphys._imports import numpy as np

import pymedphys
import pymedphys._losslessjpeg


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
