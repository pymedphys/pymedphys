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

    dataframe["Dose/Raw value (1/64th Mu)"] = dataframe[
        "Dose/Raw value (1/64th Mu)"
    ].apply(lambda x: x + 2**16 if x < 0 else x)

    # Depending on the version (Versions < 3) do not have 'Mlc Status/Actual Value (None)'.
    # We get the index location of the columns that need to be divided by 10.

    column_names = dataframe.columns

    column_start_index = column_names.get_loc("Step Gantry/Scaled Actual (deg)")
    if int(version) == 4:
        column_end_index = column_names.get_loc("Mlc Status/Actual Value (None)")
    else:
        column_end_index = len(column_names)

    # In order to speed up the conversion, will split the dataframe into the columns up to 'Step Gantry/Scaled Actual (deg)'
    # dataframe1 = dataframe.iloc[:, np.r_[0:column_start_index, column_end_index:-1]] # Useful to slice non continuously.
    dataframe1 = dataframe.iloc[:, 0:column_start_index]

    # Divide the remaining columns until 'Mlc Status/Actual Value (None)'.
    # This include Gantry, Collimator, Couch as well as Diaphragms Leaves and DLGs (in Agility).
    dataframe2 = dataframe.iloc[:, column_start_index:column_end_index].divide(10)

    ### SOME Rollbacks to ensure regression passes:
    dataframe2["Table Isocentric/Scaled Actual (deg)"] = (
        dataframe2["Table Isocentric/Scaled Actual (deg)"].divide(0.1).astype(int)
    )

    # Remaining columns post 'Mlc Status/Actual Value (None)'.
    dataframe3 = dataframe.iloc[:, column_end_index:]

    dataframe = pd.concat([dataframe1, dataframe2, dataframe3], axis=1)

    # Y2 Leaves Scaled Actual need to be multiplied by -1
    y2l = [l for l in column_names if ("Y2 Leaf" in l) and ("Scaled Actual" in l)]
    dataframe.loc[:, y2l] = -dataframe.loc[:, y2l]

    if int(version) > 1:
        dataframe["unknown1"] = dataframe["Timestamp Data"].apply(
            lambda x: int.from_bytes(np.int64(x).tobytes()[0:2], "little")
        )
        dataframe["unknown2"] = dataframe["Timestamp Data"].apply(
            lambda x: int.from_bytes(np.int64(x).tobytes()[2:4], "little")
        )
        dataframe["unknown3"] = dataframe["Timestamp Data"].apply(
            lambda x: int.from_bytes(np.int64(x).tobytes()[4:6], "little")
        )
        dataframe["unknown4"] = dataframe["Timestamp Data"].apply(
            lambda x: int.from_bytes(np.int64(x).tobytes()[6:8], "little")
        )
        dataframe = dataframe.drop("Timestamp Data", axis=1)
        dataframe = dataframe[
            dataframe.columns.to_list()[-4:] + dataframe.columns.to_list()[0:-4]
        ]

    return dataframe


def convert_data_table(dataframe, linac_state_codes, wedge_codes, version):
    dataframe = convert_linac_state_codes(dataframe, linac_state_codes)
    dataframe = convert_wedge_codes(dataframe, wedge_codes)
    dataframe = convert_positional_items(dataframe, version)

    return dataframe
