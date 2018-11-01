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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Test end to end conversion agrees."""

from glob import glob
import os
from contextlib import contextmanager

import numpy as np
import pandas as pd

from pymedphys.trf import trf2csv

CONVERTED_TAG = '_test_comparison'

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/trf")


# TODO need to include header test


@contextmanager
def file_teardown(converted_csv_file):
    yield
    os.remove(converted_csv_file)


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


def convert_and_check(filepath):
    extension_removed = os.path.splitext(filepath)[0]
    reference_csv_file = "{}.csv".format(extension_removed)
    converted_csv_file = "{}{}.csv".format(
        extension_removed, CONVERTED_TAG)
    assert os.path.exists(reference_csv_file), "Reference file should exist"

    if os.path.exists(converted_csv_file):
        os.remove(converted_csv_file)

    with file_teardown(converted_csv_file):
        trf2csv(filepath, csv_filepath=converted_csv_file)

        reference_dataframe = pd.read_csv(
            reference_csv_file, skiprows=9, index_col=0)
        del reference_dataframe[reference_dataframe.columns[-1]]

        converted_dataframe = pd.read_csv(converted_csv_file, index_col=0)

        compare_reference_to_converted(
            reference_dataframe, converted_dataframe)


def test_conversions():
    trf_files = glob(os.path.join(DATA_DIRECTORY, '*.trf'))

    for filepath in trf_files:
        convert_and_check(filepath)
