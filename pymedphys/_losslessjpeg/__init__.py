import functools
import os
import pathlib
import platform
import stat
import subprocess

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


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.ppm")

    jpeg_path = get_jpeg_executable()

    subprocess.check_call([str(jpeg_path), str(input_filepath), str(output_filepath)])
