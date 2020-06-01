import importlib
import pathlib

from pymedphys._imports import imageio, libjpeg

import pymedphys


def imread(input_filepath):
    with open(input_filepath, "rb") as f:
        im = libjpeg.decode(f.read())

    return im


def convert_lossless_jpeg(input_filepath, output_filepath=None):
    input_filepath = pathlib.Path(input_filepath)
    if output_filepath is None:
        output_filepath = input_filepath.parent.joinpath(f"{input_filepath.stem}.tif")

    im = imread(input_filepath)
    imageio.imwrite(str(output_filepath), im, format="TIFF")
