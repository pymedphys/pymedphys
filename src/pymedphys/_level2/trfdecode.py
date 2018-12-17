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


"""This is a placeholder file awaiting the required go ahead for public
release.
"""


# pylint: disable=W0401,W0614

IMPORTS = []

# from decode_trf import *  # nopep8


try:
    from decode_trf import *
except ImportError:
    Warning(
        "You need to have the decode_trf library to be able to decode `.trf` "
        "files. Please contact `me@simonbiggs.net` regarding access to this "
        "library.")

    from typing import List

    import attr

    import numpy as np
    import pandas as pd

    from .._level1.typedeliverydata import DeliveryData

    @attr.s
    class Header(object):
        machine = attr.ib()
        date = attr.ib()
        timezone = attr.ib()
        field_label = attr.ib()
        field_name = attr.ib()

    def not_implemented_error():
        raise NotImplementedError(
            "You need to have the decode_trf library to be able to decode `.trf` "
            "files. Please contact `me@simonbiggs.net` regarding access to this "
            "library.")

    def trf2pandas(filepath):
        not_implemented_error()

    def delivery_data_from_logfile(logfile_path):
        not_implemented_error()

    def decode_data_item(row, group, byteorder) -> int:
        not_implemented_error()

    def decode_column(raw_table_rows: List[str], column_number: int) -> np.ndarray:
        not_implemented_error()

    def decode_table_data(raw_table_rows: List[str]) -> np.ndarray:
        not_implemented_error()

    def create_dataframe(data, column_names, time_increment):
        not_implemented_error()

    def convert_numbers_to_string(name, lookup, column: pd.core.series.Series):
        not_implemented_error()

    def convert_linac_state_codes(dataframe, linac_state_codes):
        not_implemented_error()

    def convert_wedge_codes(dataframe, wedge_codes):
        not_implemented_error()

    def apply_negative(column):
        not_implemented_error()

    def convert_applying_negative(dataframe):
        not_implemented_error()

    def negative_and_divide_by_10(column: pd.core.series.Series):
        not_implemented_error()

    def convert_negative_and_divide_by_10(dataframe: pd.core.frame.DataFrame):
        not_implemented_error()

    def convert_remaining(dataframe: pd.core.frame.DataFrame):
        not_implemented_error()

    def convert_data_table(dataframe: pd.core.frame.DataFrame, linac_state_codes,
                           wedge_codes):
        not_implemented_error()

    def extract_header(trf_contents):
        not_implemented_error()

    def convert_header_section_to_string(section):
        not_implemented_error()

    def decode_header(trf_contents):
        not_implemented_error()

    def decode_header_from_file(filepath):
        not_implemented_error()

    def pull_grouped_header(trf_contents):
        not_implemented_error()

    def determine_header_length(trf_contents):
        not_implemented_error()

    def decode_trf(filepath):
        not_implemented_error()
