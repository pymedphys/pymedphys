# Copyright (C) 2018 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Decodes trf file.
"""

import pandas as pd

from .header import Header, decode_header, determine_header_length
from .table import decode_trf_table


def trf2pandas(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    trf_header_contents, trf_table_contents = split_into_header_table(trf_contents)

    header_dataframe = header_as_dataframe(trf_header_contents)

    table_dataframe = decode_trf_table(trf_table_contents)

    return header_dataframe, table_dataframe


read_trf = trf2pandas


def split_into_header_table(trf_contents):
    header_length = determine_header_length(trf_contents)

    trf_header_contents = trf_contents[0:header_length]
    trf_table_contents = trf_contents[header_length::]

    return trf_header_contents, trf_table_contents


def header_as_dataframe(trf_header_contents):
    header = decode_header(trf_header_contents)

    return pd.DataFrame([header], columns=Header._fields)


def decode_trf(filepath):
    """DEPRECATED
    """
    _, table_dataframe = trf2pandas(filepath)

    return table_dataframe
