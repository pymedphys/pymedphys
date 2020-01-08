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


import os

from pymedphys._imports import numpy as np

from .core import pull_mephysto_data, pull_mephysto_item, pull_mephysto_number
from .mcc2csv import file_output


def load_single_item(filepath, index):
    distance, relative_dose, scan_curvetype, scan_depth = load_mephysto(filepath)

    return (
        distance[index],
        relative_dose[index],
        scan_curvetype[index],
        scan_depth[index],
    )


def load_mephysto(filepath, output_to_file=False, output_directory=None, sort=True):
    """Input the filepath of a mephysto .mcc file and return the data of the
    scans in four lists, distance, relative_dose, scan_curvetype, and
    scan_depth. Each respective element in these lists corresponds to an
    individual scan.
    """
    # Open the file and store the contents in file_contents
    with open(filepath) as file_pointer:
        file_contents = np.array(file_pointer.readlines())

    # Use the functions defined within mccread.py to pull the desired data
    distance, relative_dose = pull_mephysto_data(file_contents)
    scan_curvetype = pull_mephysto_item("SCAN_CURVETYPE", file_contents)
    scan_depth = pull_mephysto_number("SCAN_DEPTH", file_contents)

    # Convert python lists into numpy arrays for easier use
    distance = np.array(distance)
    relative_dose = np.array(relative_dose)
    scan_curvetype = np.array(scan_curvetype)
    scan_depth = np.array(scan_depth)

    # If the user requests to sort the data (which is default) the loaded
    # mephysto files are organised so that PDDs are first, then inplane
    # profiles, then crossplane profiles.
    if sort:
        # Find the references for where the scan type is the relevant type
        # and then use the "hstack" function to join the references together.
        sort_ref = np.hstack(
            [
                np.where(scan_curvetype == "PDD")[0],  # reference of PDDs
                np.where(scan_curvetype == "INPLANE_PROFILE")[0],  # inplane ref
                np.where(scan_curvetype == "CROSSPLANE_PROFILE")[0],  # crossplane
            ]
        )

        # Confirm that the length of sort_ref is the same as scan_curvetype.
        # This will be false if there exists an unexpected scan_curvetype.
        assert len(sort_ref) == len(scan_curvetype)

        # Apply the sorting reference to each of the relevant variables.
        distance = distance[sort_ref]
        relative_dose = relative_dose[sort_ref]
        scan_curvetype = scan_curvetype[sort_ref]
        scan_depth = scan_depth[sort_ref]

    # Output csv's if "output_to_file" is True
    if output_to_file:

        # If user didn't define an output_directory use a default one
        if output_directory is None:
            # Define output directory as a mephysto folder
            filepath_directory = os.path.dirname(filepath)
            filename = os.path.splitext(os.path.basename(filepath))[0]
            output_directory = os.path.join(filepath_directory, filename)

        # If the output directory does not exist create it
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        # Call the file_output function within csvoutput.py
        file_output(
            output_directory, distance, relative_dose, scan_curvetype, scan_depth
        )

    return distance, relative_dose, scan_curvetype, scan_depth
