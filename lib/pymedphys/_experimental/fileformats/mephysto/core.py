# Copyright (C) 2017 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from pymedphys._imports import numpy as np


def find_scan_index(file_contents):
    """Searches through the mephysto file for where the BEGIN_SCAN and END_SCAN
    appear. This region contains all of the information for a given scan within
    the mephysto file. Returns a list of ranges which span each scan region.
    """
    # Find the positions of all BEGIN_SCAN
    # Demo of match -- https://regex101.com/r/lR4pS2/2
    # Demo of ignoring "BEGIN_SCAN_DATA" -- https://regex101.com/r/lR4pS2/4
    # Basic guide to regular expressions (regex):
    #    http://www.regular-expressions.info/quickstart.html
    begin_scan_index = np.array(
        [
            i
            for i, item in enumerate(file_contents)
            if re.search(r"^\tBEGIN_SCAN\s\s\d+$", item)
        ]
    ).astype(int)

    # Find the positions of all END_SCAN
    # Regex demo here -- https://regex101.com/r/lR4pS2/3
    end_scan_index = np.array(
        [
            i
            for i, item in enumerate(file_contents)
            if re.search(r"^\tEND_SCAN\s\s\d+$", item)
        ]
    ).astype(int)

    # Convert the indices into the range type allowing for easy looping
    scan_index = [
        range(begin_scan_index[i] + 1, end_scan_index[i])
        for i in range(len(begin_scan_index))
    ]

    return scan_index


def find_data_index(file_contents):
    """Searches through the mephysto file for where the BEGIN_DATA and END_DATA
    appear. This region contains only the raw data in column format. Returns a
    list of ranges which span each scan region.
    """
    # Find the positions of BEGIN_DATA
    # Demo of match -- https://regex101.com/r/lR4pS2/5
    begin_data_index = np.array(
        [
            i
            for i, item in enumerate(file_contents)
            if re.search(r"^\t\tBEGIN_DATA$", item)
        ]
    ).astype(int)

    # Find the positions of END_DATA
    # Demo of match -- https://regex101.com/r/lR4pS2/6
    end_data_index = np.array(
        [
            i
            for i, item in enumerate(file_contents)
            if re.search(r"^\t\tEND_DATA$", item)
        ]
    ).astype(int)

    # Convert the indices into the range type allowing for easy looping
    data_index = [
        range(begin_data_index[i] + 1, end_data_index[i])
        for i in range(len(begin_data_index))
    ]

    return data_index


def pull_mephysto_item(string, file_contents):
    """Steps through each scan region searching for a mephysto parameter that
    matches the requested string. Returns an array filled with the results for
    all scans that have a match. If a scan does not have a parameter matching
    the request then np.nan is returned.
    """
    scan_index = find_scan_index(file_contents)

    # Format the input string for use in a regex search
    string_test = re.escape(string)

    result = []
    # Loop over each scan index searching for requested parameter
    for index in scan_index:
        # See if any parameters match within this scan
        match = np.array(
            [
                re.match(r"^\t\t" + string_test + "=(.*)$", item) is not None
                for item in file_contents[index]
            ]
        )

        # If there is a single match then return the result
        if np.sum(match) == 1:
            relevant_line = file_contents[index][match][0]
            # Return the value that is after the equal sign
            # Example -- https://regex101.com/r/lR4pS2/7
            result.append(
                re.search(r"^\t\t" + string_test + "=(.*)$", relevant_line).group(1)
            )

        # If there is no matches return np.nan
        elif np.sum(match) == 0:
            result.append(np.nan)

        # If there is more than one match raise an error
        else:
            raise ValueError("More than one item has this label")

    return np.array(result)


def pull_mephysto_number(string, file_contents):
    """Pulls data using pull_mephysto_item and returns the result to the user
    as a float.
    """
    result = pull_mephysto_item(string, file_contents)
    return result.astype(float)


def pull_mephysto_data(file_contents):
    """Pull the distance and relative dose from the mephysto file contents.
    Will only be able to return data if the data is stored in two columns. Some
    mephysto scans use three or more columns, for these this function will have
    to be updated.
    """
    scan_index = find_scan_index(file_contents)
    data_index = find_data_index(file_contents)

    # Confirm that each data index is within the expected scan index. Raise an
    # error if it is not.
    for i in range(len(scan_index)):  # pylint: disable = consider-using-enumerate
        assert (scan_index[i][0] < data_index[i][0]) & (
            scan_index[i][-1] > data_index[i][-1]
        )

    distance = []
    # Loop through the data index and return all of the first column
    for index in data_index:
        # Demo of regex -- https://regex101.com/r/lR4pS2/10
        distance.append(
            np.array(
                [
                    re.search(
                        r"^\t\t\t([-+]?\d+\.\d+)\t\t(\d+\.\d+E[-+]?\d+)", item
                    ).group(1)
                    for item in file_contents[index]
                ]
            ).astype(float)
        )

    relative_dose = []
    # Loop through the data index and return all of the second column
    for index in data_index:
        relative_dose.append(
            np.array(
                [
                    re.search(
                        r"^\t\t\t([-+]?\d+\.\d+)\t\t(\d+\.\d+E[-+]?\d+)", item
                    ).group(2)
                    for item in file_contents[index]
                ]
            ).astype(float)
        )

    return distance, relative_dose
