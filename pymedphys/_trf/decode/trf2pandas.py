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

from pymedphys._imports import pandas as pd

from .header import Header, decode_header
from .partition import split_into_header_table
from .table import decode_trf_table


def trf2pandas(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

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
