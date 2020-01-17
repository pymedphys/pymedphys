import functools
import os
import pathlib
import platform
import stat
import subprocess
import tempfile

from pymedphys._imports import imageio

import pymedphys


@functools.lru_cache(maxsize=1)
def get_jpeg_executable():
    system = platform.system()

    if system == "Windows":
        return pymedphys.data_path("jpeg.exe")

    if system == "Darwin":
        raise OSError(
            "No lossless jpeg binary available for macOS. If you wish "
            "to have macOS support for this function please email me at "
            "me@simonbiggs.net and we can get it included."
        )

    if system == "Linux":
        jpeg_path = pymedphys.data_path("jpeg")
        st = os.stat(jpeg_path)
        os.chmod(jpeg_path, st.st_mode | stat.S_IEXEC)

        return jpeg_path

    raise OSError(
        "You are running an unknown platform. If you would like this "
        "platform supported please email me at me@simonbiggs.net"
    )


def imread(input_filepath):
    input_filepath = pathlib.Path(input_filepath)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = pathlib.Path(temp_dir)
        temp_path = temp_dir_path.joinpath(input_filepath.name)

        convert_lossless_jpeg(input_filepath, output_filepath=temp_path)

        im = imageio.imread(temp_path)

    return im


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.ppm")

    jpeg_path = get_jpeg_executable()

    subprocess.check_call([str(jpeg_path), str(input_filepath), str(output_filepath)])
