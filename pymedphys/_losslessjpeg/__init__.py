import functools
import os
import pathlib
import stat
import subprocess
import sys

import pymedphys


@functools.lru_cache(maxsize=1)
def get_jpeg_executable():
    if sys.platform == "win32":
        jpeg_path = pymedphys.data_path("jpeg.exe")
    else:
        jpeg_path = pymedphys.data_path("jpeg")
        st = os.stat(jpeg_path)
        os.chmod(jpeg_path, st.st_mode | stat.S_IEXEC)

    return jpeg_path


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.ppm")

    jpeg_path = get_jpeg_executable()

    subprocess.check_call([str(jpeg_path), str(input_filepath), str(output_filepath)])
