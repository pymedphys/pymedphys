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

import pathlib
import tempfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest

import pymedphys
from pymedphys._trf.decode.trf2csv import trf2csv

# TODO need to include header test


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
                converted_dataframe[column].values,
                "The {} column should be equal".format(column),
            )


def convert_and_check_against_baseline(filepath: pathlib.Path, output_directory):
    baseline_csv_file = filepath.parent.joinpath(filepath.stem + "_table.csv")
    baseline_dataframe = pd.read_csv(baseline_csv_file, index_col=0)

    convert_and_check(filepath, output_directory, baseline_dataframe)


def convert_and_check_against_reference(filepath: pathlib.Path, output_directory):
    reference_csv_file = filepath.with_suffix(".csv")
    reference_dataframe = pd.read_csv(reference_csv_file, skiprows=9, index_col=0)
    del reference_dataframe[reference_dataframe.columns[-1]]

    convert_and_check(filepath, output_directory, reference_dataframe)


def convert_and_check(filepath: pathlib.Path, output_directory, reference_dataframe):
    _, table_filepath = trf2csv(filepath, output_directory=output_directory)
    converted_dataframe = pd.read_csv(table_filepath, index_col=0)

    compare_reference_to_converted(reference_dataframe, converted_dataframe)


@pytest.mark.slow
def test_conversions():
    data_paths = pymedphys.zip_data_paths("trf-references-and-baselines.zip")

    files_with_references = [
        path
        for path in data_paths
        if path.parent.name == "with_reference" and path.suffix == ".trf"
    ]

    assert len(files_with_references) >= 5

    files_without_references = [
        path
        for path in data_paths
        if path.parent.name == "with_baseline" and path.suffix == ".trf"
    ]

    assert len(files_without_references) >= 4

    with tempfile.TemporaryDirectory() as output_directory:
        for filepath in files_with_references:
            convert_and_check_against_reference(filepath, output_directory)

        for filepath in files_without_references:
            convert_and_check_against_baseline(filepath, output_directory)
