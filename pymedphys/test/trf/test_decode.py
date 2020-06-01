# Copyright (C) 2018 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Test end to end conversion agrees."""

import os
from contextlib import contextmanager
from glob import glob

import numpy as np
import pandas as pd

from pymedphys._trf.trf2csv import trf2csv

HEADER_TAG = "_header"
TABLE_TAG = "_table"

DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../data/trf")


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
        reference_dataframe.columns,
        converted_dataframe.columns,
        "Columns should be equal.",
    )

    np.testing.assert_array_equal(
        reference_dataframe.index, converted_dataframe.index, "Index should be equal."
    )

    if not np.all(reference_dataframe.values == converted_dataframe.values):
        for column in reference_dataframe.columns:
            np.testing.assert_array_equal(
                reference_dataframe[column].values,
                reference_dataframe[column].values,
                "The {} column should be equal".format(column),
            )


def get_filepaths(filepath):
    extension_removed = os.path.splitext(filepath)[0]
    reference_csv_file = "{}.csv".format(extension_removed)

    converted_header_csv_filepath = "{}{}.csv".format(extension_removed, HEADER_TAG)
    converted_table_csv_filepath = "{}{}.csv".format(extension_removed, TABLE_TAG)

    converted_filepaths = [converted_header_csv_filepath, converted_table_csv_filepath]

    return reference_csv_file, converted_filepaths


def convert_and_check(filepath):

    reference_csv_file, converted_filepaths = get_filepaths(filepath)

    assert os.path.exists(reference_csv_file), "Reference file should exist"

    with files_teardown(converted_filepaths):
        trf2csv(filepath)

        reference_dataframe = pd.read_csv(reference_csv_file, skiprows=9, index_col=0)
        del reference_dataframe[reference_dataframe.columns[-1]]

        converted_table_csv_filepath = converted_filepaths[1]

        converted_dataframe = pd.read_csv(converted_table_csv_filepath, index_col=0)

        compare_reference_to_converted(reference_dataframe, converted_dataframe)


def test_conversions():
    reference_files = glob(os.path.join(DATA_DIRECTORY, "elekta_reference", "*.trf"))

    for filepath in reference_files:
        convert_and_check(filepath)

    integrity4_files = glob(os.path.join(DATA_DIRECTORY, "integrity4", "*.trf"))

    for filepath in integrity4_files:
        _, converted_filepaths = get_filepaths(filepath)
        with files_teardown(converted_filepaths):
            trf2csv(filepath)
