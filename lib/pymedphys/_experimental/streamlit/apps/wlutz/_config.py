import pathlib

import pymedphys
from pymedphys._streamlit.utilities import config as st_config


def download_demo_data():
    cwd = pathlib.Path.cwd()
    pymedphys.zip_data_paths("wlutz-demo-files.zip", extract_directory=cwd)

    return cwd.joinpath("wlutz-demo-files")


def get_config(demo_mode):
    if demo_mode:
        path = download_demo_data()
    else:
        path = None

    return st_config.get_config(path)
