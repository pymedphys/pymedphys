# Copyright (C) 2018 Simon Biggs

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


"""Test end to end conversion agrees."""

from glob import glob
import os
from contextlib import contextmanager

import pytest

import numpy as np
import pandas as pd

from pymedphys.trf import trf2csv

HEADER_TAG = '_header'
TABLE_TAG = '_table'

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/trf")


pytest.skip(
    "Skipping decode_trf tests, the library can't be made public.",
    allow_module_level=True)


# TODO need to include header test


@contextmanager
def files_teardown(files_to_delete):
    for a_file in files_to_delete:
        if os.path.exists(a_file):
            os.remove(a_file)

    yield

    for a_file in files_to_delete:
        os.remove(a_file)


def compare_reference_to_converted(reference_dataframe, converted_dataframe):
    np.testing.assert_array_equal(
        reference_dataframe.columns, converted_dataframe.columns,
        "Columns should be equal.")

    np.testing.assert_array_equal(
        reference_dataframe.index, converted_dataframe.index,
        "Index should be equal.")

    if not np.all(reference_dataframe.values == converted_dataframe.values):
        for column in reference_dataframe.columns:
            np.testing.assert_array_equal(
                reference_dataframe[column].values,
                reference_dataframe[column].values,
                "The {} column should be equal".format(column))


def get_filepaths(filepath):
    extension_removed = os.path.splitext(filepath)[0]
    reference_csv_file = "{}.csv".format(extension_removed)

    converted_header_csv_filepath = "{}{}.csv".format(
        extension_removed, HEADER_TAG)
    converted_table_csv_filepath = "{}{}.csv".format(
        extension_removed, TABLE_TAG)

    converted_filepaths = [
        converted_header_csv_filepath, converted_table_csv_filepath
    ]

    return reference_csv_file, converted_filepaths


def convert_and_check(filepath):

    reference_csv_file, converted_filepaths = get_filepaths(filepath)

    assert os.path.exists(reference_csv_file), "Reference file should exist"

    with files_teardown(converted_filepaths):
        trf2csv(filepath)

        reference_dataframe = pd.read_csv(
            reference_csv_file, skiprows=9, index_col=0)
        del reference_dataframe[reference_dataframe.columns[-1]]

        converted_table_csv_filepath = converted_filepaths[1]

        converted_dataframe = pd.read_csv(
            converted_table_csv_filepath, index_col=0)

        compare_reference_to_converted(
            reference_dataframe, converted_dataframe)


def test_conversions():
    reference_files = glob(
        os.path.join(DATA_DIRECTORY, 'elekta_reference', '*.trf'))

    for filepath in reference_files:
        try:
            convert_and_check(filepath)
        except NotImplementedError:
            pytest.skip(
                "`decode_trf` doesn't appear to be installed, skipping this "
                "test."
            )

    integrity4_files = glob(
        os.path.join(DATA_DIRECTORY, 'integrity4', '*.trf'))

    for filepath in integrity4_files:
        try:
            _, converted_filepaths = get_filepaths(filepath)
            with files_teardown(converted_filepaths):
                trf2csv(filepath)

        except NotImplementedError:
            pytest.skip(
                "`decode_trf` doesn't appear to be installed, skipping this "
                "test."
            )
