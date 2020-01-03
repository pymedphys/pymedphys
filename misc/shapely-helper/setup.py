#!/usr/bin/env python
# coding: utf-8

# mypy: ignore-errors

import platform
from distutils.core import setup

if platform.system() == "Windows":
    URL_BASE = "https://github.com/pymedphys/pymedphys/releases/download/v0.14.0/"

    WINDOWS_INSTALL_URLS = {
        ("i386", "3.6"): f"{URL_BASE}Shapely-1.6.4.post2-cp36-cp36m-win32.whl",
        ("AMD64", "3.6"): f"{URL_BASE}Shapely-1.6.4.post2-cp36-cp36m-win_amd64.whl",
        ("i386", "3.7"): f"{URL_BASE}Shapely-1.6.4.post2-cp37-cp37m-win32.whl",
        ("AMD64", "3.7"): f"{URL_BASE}Shapely-1.6.4.post2-cp37-cp37m-win_amd64.whl",
        ("i386", "3.8"): f"{URL_BASE}Shapely-1.6.4.post2-cp38-cp38m-win32.whl",
        ("AMD64", "3.8"): f"{URL_BASE}Shapely-1.6.4.post2-cp38-cp38m-win_amd64.whl",
    }

    python_version = platform.python_version_tuple()
    major_minor_python_version = f"{python_version[0]}.{python_version[1]}"

    install_requires = [
        f"shapely @ {WINDOWS_INSTALL_URLS[(platform.machine(), major_minor_python_version)]}"
    ]

else:
    install_requires = ["shapely"]


setup_args = dict(
    name="shapely-helper",
    version="1.6.4.post2",
    description="Helper to install shapely with pip.",
    author="Simon Biggs",
    author_email="me@simonbiggs.net",
    py_modules=["shapely-helper"],
    install_requires=install_requires,
)

if __name__ == "__main__":
    setup(**setup_args)
