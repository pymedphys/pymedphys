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

from typing import List

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd

from .constants import CONFIG
from .header import determine_header_length

GROUPING_OPTIONS = {
    "integrityv3": {"line_grouping": 700, "linac_state_codes_column": 2},
    "integrityv4": {"line_grouping": 708, "linac_state_codes_column": 6},
    "unity_experimental": {"line_grouping": 700, "linac_state_codes_column": 6},
}

# LINE_GROUPING_OPTIONS = {
#     item["line_grouping"]: item["linac_state_codes_column"]
#     for _, item in GROUPING_OPTIONS.items()
# }


def decode_rows(
    trf_table_contents,
    input_line_grouping=None,
    input_linac_state_codes_column=None,
    reference_state_code_keys=None,
):
    table_byte_length = len(trf_table_contents)

    if input_line_grouping is not None or input_linac_state_codes_column is not None:
        if input_line_grouping is None or input_linac_state_codes_column is None:
            raise ValueError(
                "If customising line grouping, need to provide both "
                "`input_line_grouping` and `input_linac_state_codes_column`"
            )

        grouping_options = {
            "custom": {
                "line_grouping": input_line_grouping,
                "linac_state_codes_column": input_linac_state_codes_column,
            }
        }
    else:
        grouping_options = GROUPING_OPTIONS

    possible_groupings = {}

    for key, item in grouping_options.items():
        grouping_option = item["line_grouping"]
        linac_state_codes_column = item["linac_state_codes_column"]

        if table_byte_length / grouping_option == table_byte_length // grouping_option:
            possible_groupings[key] = (grouping_option, linac_state_codes_column)

    if not possible_groupings:
        raise ValueError("Unexpected number of bytes within file.")

    if reference_state_code_keys is None:
        reference_state_codes = set(
            np.array(list(CONFIG["linac_state_codes"].keys())).astype(int)
        )
    else:
        reference_state_codes = set(reference_state_code_keys)

    decoded_results = []
    possible_column_adjustment_key = []
    for key, (line_grouping, linac_state_codes_column) in possible_groupings.items():
        rows = [
            trf_table_contents[i : i + line_grouping]
            for i in range(0, len(trf_table_contents), line_grouping)
        ]

        result = decode_table_data(rows, line_grouping)
        tentative_state_codes = result[  # pylint: disable = unsubscriptable-object
            :, linac_state_codes_column
        ]

        if set(tentative_state_codes).issubset(reference_state_codes):
            decoded_results.append(decode_table_data(rows, line_grouping))
            possible_column_adjustment_key.append(key)

    if not decoded_results:
        raise ValueError("Decoded table didn't pass shape test")

    if len(decoded_results) > 1:
        raise ValueError("Can't determine version of trf file from table shape")

    decoded_rows = decoded_results[0]
    column_adjustment_key = possible_column_adjustment_key[0]

    return decoded_rows, column_adjustment_key


def decode_rows_from_file(filepath):
    with open(filepath, "rb") as file:
        trf_contents = file.read()

    header_length = determine_header_length(trf_contents)
    trf_table_contents = trf_contents[header_length::]

    decoded_rows, _ = decode_rows(trf_table_contents)

    return decoded_rows


def get_column_names(column_adjustment_key):
    column_names = CONFIG["column_names"]

    if column_adjustment_key == "integrityv3":
        return column_names

    filler_columns = [f"unknown{item}" for item in range(1, 5)]

    column_names = filler_columns + column_names

    if column_adjustment_key == "integrityv4":
        return column_names

    if column_adjustment_key != "unity_experimental":
        raise ValueError("Unexpected `column_adjustment_key`")

    column_names = [item for item in column_names if "Dlg" not in item]

    return column_names


def decode_trf_table(trf_table_contents):
    decoded_rows, column_adjustment_key = decode_rows(trf_table_contents)

    column_names = get_column_names(column_adjustment_key)

    number_of_columns = len(decoded_rows[0, :])

    if len(column_names) != number_of_columns:
        raise ValueError("Columns names don't agree with number of columns")

    table_dataframe = create_dataframe(
        decoded_rows, column_names, CONFIG["time_increment"]
    )

    convert_data_table(
        table_dataframe, CONFIG["linac_state_codes"], CONFIG["wedge_codes"]
    )

    return table_dataframe


def decode_data_item(row, group, byteorder) -> int:
    """Converts the bytes of data items into an integer."""
    return int.from_bytes(row[group], byteorder=byteorder)


def decode_column(raw_table_rows: List[str], column_number: int):
    """Decode all of the items in a given column."""
    grouping = 2
    i = column_number * grouping
    group = slice(i, i + grouping)
    byteorder = "little"

    column = np.array(
        [decode_data_item(row, group, byteorder) for row in raw_table_rows]
    )

    return column


def decode_table_data(raw_table_rows: List[str], line_grouping):
    """Decode the table into integer values."""

    result = []
    for column_number in range(0, line_grouping // 2):
        result.append(decode_column(raw_table_rows, column_number))

    return np.array(result).T


def create_dataframe(data, column_names, time_increment):
    """Converts the provided data into a pandas dataframe."""
    dataframe = pd.DataFrame(data=data, columns=column_names)
    dataframe.index = np.round(dataframe.index * time_increment, 2)

    return dataframe


def convert_numbers_to_string(name, lookup, column):
    dtype = np.array([item for _, item in lookup.items()]).dtype
    result = np.empty_like(column).astype(dtype)
    result[:] = ""

    for i, item in lookup.items():
        result[column.values == int(i)] = item

    if np.any(result == ""):
        print(lookup)
        print(np.where(result == ""))
        print(column[result == ""].values)
        unconverted_entries = np.unique(column[result == ""])
        raise Exception(
            "The conversion lookup list for converting {} is incomplete. "
            "The following data numbers were not converted:\n"
            "{}\n"
            "Please update the trf2csv conversion script to include these "
            "in its definitions.".format(name, unconverted_entries)
        )

    return result


def convert_linac_state_codes(dataframe, linac_state_codes):
    name = "linac state"
    key = "Linac State/Actual Value (None)"
    dataframe[key] = convert_numbers_to_string(name, linac_state_codes, dataframe[key])


def convert_wedge_codes(dataframe, wedge_codes):
    name = "wedge"
    key = "Wedge Position/Actual Value (None)"
    dataframe[key] = convert_numbers_to_string(name, wedge_codes, dataframe[key])


def apply_negative(column):
    result = np.ones_like(column).astype(np.float64) * np.nan
    negative_values = column.values > 2 ** 15

    result[negative_values] = column[negative_values] - 2 ** 16
    result[np.invert(negative_values)] = column[np.invert(negative_values)]

    if np.any(np.isnan(result)):
        raise Exception("Not all column values were converted")

    return result


def convert_applying_negative(dataframe):
    keys = [
        "Control point/Actual Value (None)",
        "Table Isocentric/Scaled Actual (deg)",
        "Table Isocentric/Positional Error (deg)",
    ]

    for key in keys:
        dataframe[key] = apply_negative(dataframe[key])


def negative_and_divide_by_10(column):
    result = apply_negative(column)
    result = result / 10

    return result


def convert_negative_and_divide_by_10(dataframe):
    keys = [
        "Step Dose/Actual Value (Mu)",
        "Step Gantry/Scaled Actual (deg)",
        "Step Gantry/Positional Error (deg)",
        "Step Collimator/Scaled Actual (deg)",
        "Step Collimator/Positional Error (deg)",
    ]

    for key in keys:
        dataframe[key] = negative_and_divide_by_10(dataframe[key])


def convert_remaining(dataframe):
    column_names = dataframe.columns

    for key in column_names[14:30]:
        dataframe[key] = negative_and_divide_by_10(dataframe[key])

    # Y2 leaves need to be multiplied by -1
    for key in column_names[30:110]:
        dataframe[key] = -negative_and_divide_by_10(dataframe[key])

    for key in column_names[110::]:
        dataframe[key] = negative_and_divide_by_10(dataframe[key])


def convert_data_table(dataframe, linac_state_codes, wedge_codes):
    convert_linac_state_codes(dataframe, linac_state_codes)
    convert_wedge_codes(dataframe, wedge_codes)

    convert_applying_negative(dataframe)
    convert_negative_and_divide_by_10(dataframe)
    convert_remaining(dataframe)
