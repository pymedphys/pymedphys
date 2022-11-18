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

# from typing import List

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd

from .constants import CONFIG

# from .header import determine_header_length

# GROUPING_OPTIONS = {
#     "integrity_v3": {"line_grouping": 700, "linac_state_codes_column": 2},
#     "integrity_v4": {"line_grouping": 708, "linac_state_codes_column": 6},
#     "unity_experimental": {"line_grouping": 700, "linac_state_codes_column": 6},
# }

# LINE_GROUPING_OPTIONS = {
#     item["line_grouping"]: item["linac_state_codes_column"]
#     for _, item in GROUPING_OPTIONS.items()
# }


# def decode_rows(
#     trf_table_contents,
#     input_line_grouping=None,
#     input_linac_state_codes_column=None,
#     reference_state_code_keys=None,
# ):
#     table_byte_length = len(trf_table_contents)

#     if input_line_grouping is not None or input_linac_state_codes_column is not None:
#         if input_line_grouping is None or input_linac_state_codes_column is None:
#             raise ValueError(
#                 "If customising line grouping, need to provide both "
#                 "`input_line_grouping` and `input_linac_state_codes_column`"
#             )

#         grouping_options = {
#             "custom": {
#                 "line_grouping": input_line_grouping,
#                 "linac_state_codes_column": input_linac_state_codes_column,
#             }
#         }
#     else:
#         grouping_options = GROUPING_OPTIONS

#     possible_groupings = {}

#     for key, item in grouping_options.items():
#         grouping_option = item["line_grouping"]
#         linac_state_codes_column = item["linac_state_codes_column"]

#         if table_byte_length / grouping_option == table_byte_length // grouping_option:
#             possible_groupings[key] = (grouping_option, linac_state_codes_column)

#     if not possible_groupings:
#         raise ValueError("Unexpected number of bytes within file.")

#     if reference_state_code_keys is None:
#         reference_state_codes = set(
#             np.array(list(CONFIG["linac_state_codes"].keys())).astype(int)
#         )
#     else:
#         reference_state_codes = set(reference_state_code_keys)

#     non_reference_state_codes_found = set()
#     decoded_results = []
#     possible_column_adjustment_key = []
#     for key, (line_grouping, linac_state_codes_column) in possible_groupings.items():
#         rows = [
#             trf_table_contents[i : i + line_grouping]
#             for i in range(0, len(trf_table_contents), line_grouping)
#         ]

#         result = decode_table_data(rows, line_grouping)
#         tentative_state_codes = result[  # pylint: disable = unsubscriptable-object
#             :, linac_state_codes_column
#         ]

#         if set(tentative_state_codes).issubset(reference_state_codes):
#             decoded_results.append(decode_table_data(rows, line_grouping))
#             possible_column_adjustment_key.append(key)
#         else:
#             non_reference_state_codes = set(tentative_state_codes).difference(
#                 reference_state_codes
#             )
#             non_reference_state_codes_found = non_reference_state_codes_found.union(
#                 non_reference_state_codes
#             )

#     if not decoded_results:
#         raise ValueError(
#             "Decoded table didn't pass shape test. While attempting to "
#             "decode the TRF logfile there were some non-reference state "
#             "codes that were found. This may be the cause of this shape "
#             "test failure. The non-reference state codes found are "
#             f"{non_reference_state_codes_found}"
#         )

#     if len(decoded_results) > 1:
#         raise ValueError("Can't determine version of trf file from table shape")

#     decoded_rows = decoded_results[0]
#     column_adjustment_key = possible_column_adjustment_key[0]

#     return decoded_rows, column_adjustment_key


# def decode_rows_from_file(filepath):
#     with open(filepath, "rb") as file:
#         trf_contents = file.read()

#     header_length = determine_header_length(trf_contents)
#     trf_table_contents = trf_contents[header_length::]

#     decoded_rows, _ = decode_rows(trf_table_contents)

#     return decoded_rows


# def get_base_column_names():
#     return CONFIG["column_names"]


# def get_column_names(column_adjustment_key):
#     column_names = get_base_column_names()

#     if column_adjustment_key == "integrity_v3":
#         return column_names

#     filler_columns = [f"unknown{item}" for item in range(1, 5)]

#     column_names = filler_columns + column_names

#     if column_adjustment_key == "integrity_v4":
#         return column_names

#     if column_adjustment_key != "unity_experimental":
#         raise ValueError("Unexpected `column_adjustment_key`")

#     column_names = [item for item in column_names if "Dlg" not in item]

#     return column_names


# def decode_trf_table(trf_table_contents):
#     decoded_rows, column_adjustment_key = decode_rows(trf_table_contents)

#     column_names = get_column_names(column_adjustment_key)

#     number_of_columns = len(decoded_rows[0, :])

#     if len(column_names) != number_of_columns:
#         raise ValueError("Columns names don't agree with number of columns")

#     table_dataframe = create_dataframe(
#         decoded_rows, column_names, CONFIG["time_increment"]
#     )

#     convert_data_table(
#         table_dataframe, CONFIG["linac_state_codes"], CONFIG["wedge_codes"]
#     )

#     return table_dataframe


# def decode_data_item(row, group, byteorder) -> int:
#     """Converts the bytes of data items into an integer."""
#     return int.from_bytes(row[group], byteorder=byteorder)


# def decode_column(raw_table_rows: List[str], column_number: int):
#     """Decode all of the items in a given column."""
#     grouping = 2
#     i = column_number * grouping
#     group = slice(i, i + grouping)
#     byteorder = "little"

#     column = np.array(
#         [decode_data_item(row, group, byteorder) for row in raw_table_rows]
#     )

#     return column


# def decode_table_data(raw_table_rows: List[str], line_grouping):
#     """Decode the table into integer values."""

#     result = []
#     for column_number in range(0, line_grouping // 2):
#         result.append(decode_column(raw_table_rows, column_number))

#     return np.array(result).T


# def apply_negative(column):
#     result = np.ones_like(column).astype(np.float64) * np.nan
#     negative_values = column.values > 2**15

#     result[negative_values] = column[negative_values] - 2**16
#     result[np.invert(negative_values)] = column[np.invert(negative_values)]

#     if np.any(np.isnan(result)):
#         raise ValueError("Not all column values were converted")

#     return result


# def convert_applying_negative(dataframe):
#     keys = [
#         "Control point/Actual Value (None)",
#         "Table Isocentric/Scaled Actual (deg)",
#         "Table Isocentric/Positional Error (deg)",
#     ]

#     for key in keys:
#         dataframe[key] = apply_negative(dataframe[key])


# def negative_and_divide_by_10(column):
#     result = apply_negative(column)
#     result = result / 10

#     return result


# def convert_negative_and_divide_by_10(dataframe):
#     keys = [
#         "Step Dose/Actual Value (Mu)",
#         "Step Gantry/Scaled Actual (deg)",
#         "Step Gantry/Positional Error (deg)",
#         "Step Collimator/Scaled Actual (deg)",
#         "Step Collimator/Positional Error (deg)",
#     ]

#     for key in keys:
#         dataframe[key] = negative_and_divide_by_10(dataframe[key])


# def convert_remaining(dataframe):
#     # The base column names are used here as they are presumed to be unchanging.
#     # Should ever the order or contents of the base configured 'column_names'
#     # change, this logic here will need to be changed.
#     base_column_names = get_base_column_names()

#     for key in base_column_names[14:30]:
#         try:
#             dataframe[key] = negative_and_divide_by_10(dataframe[key])
#         except KeyError:
#             if "Dlg" in key:
#                 # Unity logfile do not have a "Dlg" record
#                 pass
#             else:
#                 raise

#     # Previously a bug crept in due to this choice of logic. When the
#     # decoding was adjusted to support Integrity 4 four extra
#     # columns were added. This resulted in this logic being applied to
#     # the wrong columns (offset by four).
#     for key in base_column_names[30:110]:
#         if "Leaf" not in key or "Y2" not in key or "Scaled Actual" not in key:
#             raise ValueError("Y2 Leaf Keys were not in their expected positions.")

#         # Y2 leaves need to be multiplied by -1
#         dataframe[key] = -negative_and_divide_by_10(dataframe[key])

#     for key in base_column_names[110::]:
#         if "Leaf" not in key:
#             raise ValueError(
#                 "The remaining leaf columns were not in their "
#                 f"expected positions. Key found was `{key}`."
#             )
#         dataframe[key] = negative_and_divide_by_10(dataframe[key])


def decode_trf_table(trf_table_contents, header_table_contents):

    version = header_table_contents["version"].values[0].astype(int)
    item_parts_length = header_table_contents["item_parts_length"].values[0].astype(int)
    item_parts = header_table_contents["item_parts"].values[0]

    decoded_rows, column_names = decode_rows(
        trf_table_contents, version, item_parts_length, item_parts
    )

    table_dataframe = create_dataframe(
        decoded_rows, column_names, CONFIG["time_increment"]
    )

    table_dataframe = convert_data_table(
        table_dataframe, CONFIG["linac_state_codes"], CONFIG["wedge_codes"], version
    )

    return table_dataframe


def decode_rows(trf_table_contents, version, item_parts_length, item_parts):

    column_names_from_dict = CONFIG["item_part_names"]
    column_names_from_data = [
        str(item_parts[i]) + "_" + str(item_parts[i + 1])
        for i in range(0, item_parts_length, 2)
    ]

    # print(CONFIG["version_row"])
    dtype = CONFIG["version_row"][str(version)]["dtype"]
    offset = CONFIG["version_row"][str(version)]["offset"]
    lg_scale = CONFIG["version_row"][str(version)]["lg_scale"]
    line_grouping = lg_scale * item_parts_length + offset

    if version == 1:

        decoded_rows = [
            np.frombuffer(
                trf_table_contents[i : i + line_grouping],
                offset=offset,
                dtype=np.dtype(dtype),
            )
            for i in range(0, len(trf_table_contents), line_grouping)
        ]
        column_names = [column_names_from_dict[c] for c in column_names_from_data]

    else:

        timestamps = [
            np.frombuffer(trf_table_contents[i : i + 8], offset=0, dtype=np.int64)
            for i in range(0, len(trf_table_contents), line_grouping)
        ]
        item_part_values_data = [
            np.frombuffer(
                trf_table_contents[i : i + line_grouping],
                offset=offset,
                dtype=np.dtype(dtype),
            )
            for i in range(0, len(trf_table_contents), line_grouping)
        ]
        decoded_rows = [
            np.concatenate((timestamps[i], item_parts))
            for i, item_parts in enumerate(item_part_values_data)
        ]
        column_names = ["Timestamp Data"] + [
            column_names_from_dict[c] for c in column_names_from_data
        ]

    return decoded_rows, column_names


def create_dataframe(data, column_names, time_increment):
    """Converts the provided data into a pandas dataframe."""
    dataframe = pd.DataFrame(data=data, columns=column_names)
    dataframe.index = np.round(dataframe.index * time_increment, 2)

    return dataframe


def convert_numbers_to_string(name, lookup, column):
    dtype = np.array([item for _, item in lookup.items()]).dtype
    result = np.empty_like(column).astype(dtype)  # pylint: disable = no-member
    result[:] = ""

    for i, item in lookup.items():
        result[column.values == int(i)] = item

    if np.any(result == ""):
        print(lookup)
        print(np.where(result == ""))
        print(column[result == ""].values)
        unconverted_entries = np.unique(column[result == ""])
        raise ValueError(
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

    return dataframe


def convert_wedge_codes(dataframe, wedge_codes):
    name = "wedge"
    key = "Wedge Position/Actual Value (None)"
    dataframe[key] = convert_numbers_to_string(name, wedge_codes, dataframe[key])

    return dataframe


def convert_positional_items(
    dataframe: "pd.core.frame.DataFrame", version: str
) -> "pd.core.frame.DataFrame":
    """Process the dataframe and convert all of the relevant positional items to divided by 10.
    The Step Dose/Actual Value (Mu) also needs to be divided by 10.
    The Y2 Leaves need to be multiplied by -1.

    Parameters
    ----------
    dataframe: pd.core.frame.DataFrame
        A Pandas Dataframe with original wedge code state in decimal format.
    version: str
        A string with the version of the TRF extracted from the header in order to do some dataframe manipulation
    Returns
    ----------
    dataframe: pd.core.frame.DataFrame
        A Pandas DataFrame with the wedge codes converted to the corresponding name.
    """

    # Divide the step dose by 10. This has to be done before because the next step will require
    # a continuous range from the gantry to the last leaf positional error. Due to the fact that the
    # wedge code has been converted to string and there are values such as
    # Dose/Raw value (1/64th Mu) and PRF Pauses/Actual Value (None) that do not require conversion,
    # we will perform this conversion first.

    dataframe["Step Dose/Actual Value (Mu)"] = dataframe[
        "Step Dose/Actual Value (Mu)"
    ].divide(10)

    # Depending on the version (Versions < 3) do not have 'Mlc Status/Actual Value (None)'.
    # We get the index location of the columns that need to be divided by 10.

    column_names = dataframe.columns

    column_start_index = column_names.get_loc("Step Gantry/Scaled Actual (deg)")
    if version == 4:
        column_end_index = column_names.get_loc("Mlc Status/Actual Value (None)")
    else:
        column_end_index = len(column_names)

    # In order to speed up the conversion, will split the dataframe into the columns up to 'Step Gantry/Scaled Actual (deg)'
    # dataframe1 = dataframe.iloc[:, np.r_[0:column_start_index, column_end_index:-1]] # Useful to slice non continuously.
    dataframe1 = dataframe.iloc[:, 0:column_start_index]

    # Divide the remaining columns until 'Mlc Status/Actual Value (None)'.
    # This include Gantry, Collimator, Couch as well as Diaphragms Leaves and DLGs (in Agility).
    dataframe2 = dataframe.iloc[:, column_start_index:column_end_index].divide(10)

    # Remaining columns post 'Mlc Status/Actual Value (None)'.
    dataframe3 = dataframe.iloc[:, column_end_index:]

    # Concatenate both dataframe
    dataframe = pd.concat([dataframe1, dataframe2, dataframe3], axis=1)

    # Y2 Leaves Scaled Actual need to be multiplied by -1
    y2l = [l for l in column_names if ("Y2 Leaf" in l) and ("Scaled Actual" in l)]
    dataframe.loc[:, y2l] = -dataframe.loc[:, y2l]

    return dataframe


def convert_data_table(dataframe, linac_state_codes, wedge_codes, version):
    dataframe = convert_linac_state_codes(dataframe, linac_state_codes)
    dataframe = convert_wedge_codes(dataframe, wedge_codes)
    dataframe = convert_positional_items(dataframe, version)

    return dataframe
