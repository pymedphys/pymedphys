# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Decodes trf file.
"""

import os
from typing import IO, Any, Union, cast

from pymedphys._imports import pandas as pd

from .header import Header, decode_header
from .partition import split_into_header_table
from .table import decode_trf_table

path_or_file_like = Union[IO, "os.PathLike[Any]"]


def trf2pandas(trf: path_or_file_like):
    file_like_trf = cast(IO, trf)
    path_like_trf = cast("os.PathLike[Any]", trf)

    try:
        trf_contents = file_like_trf.read()
    except AttributeError:
        with open(path_like_trf, "rb") as f:
            trf_contents = f.read()

    trf_header_contents, trf_table_contents = split_into_header_table(trf_contents)

    header_dataframe = header_as_dataframe(trf_header_contents)

    table_dataframe = decode_trf_table(trf_table_contents)

    return header_dataframe, table_dataframe


read_trf = trf2pandas


def header_as_dataframe(trf_header_contents):
    header = decode_header(trf_header_contents)

    return pd.DataFrame([header], columns=Header._fields)


def decode_trf(filepath):
    """DEPRECATED
    """
    _, table_dataframe = trf2pandas(filepath)

    return table_dataframe
