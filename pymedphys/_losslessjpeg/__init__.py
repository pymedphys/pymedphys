import pathlib
import subprocess
import sys

import pymedphys


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.ppm")

    if sys.platform == "win32":
        jpeg_path = pymedphys.data_path("jpeg.exe")
    else:
        jpeg_path = pymedphys.data_path("jpeg")

    subprocess.check_call([str(jpeg_path), str(input_filepath), str(output_filepath)])
