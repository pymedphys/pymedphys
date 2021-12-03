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
from pymedphys._imports import pandas as pd


def file_output(output_directory, distance, relative_dose, scan_curvetype, scan_depth):
    """Store the loaded mephysto data into csv files for easy user confirmation
    and use.
    """
    # Determines the filepaths for the output
    filepaths = determine_output_filepaths(output_directory, scan_curvetype, scan_depth)

    columns = ["distance (mm)", "relative dose"]

    # Loop over each curvetype and save the data to csv
    for i, _ in enumerate(scan_curvetype):
        # Stacks the data into one array and transposes into column orientation
        data = np.vstack([distance[i], relative_dose[i]]).T

        # Use pandas to save data to csv
        df = pd.DataFrame(data, columns=columns)
        df.to_csv(filepaths[i])


def determine_output_filepaths(output_directory, scan_curvetype, scan_depth):
    """Determine a useful filepath for the saving of each mephysto scan."""
    filepaths = []

    # Loop over each scan curvetype creating a relevant filepath
    for i, curvetype in enumerate(scan_curvetype):
        if curvetype == "PDD":
            # Create the filename to be pdd_[number].csv
            filepaths.append(
                os.path.join(output_directory, "pdd_[{0:d}].csv".format(i))
            )

        elif curvetype == "INPLANE_PROFILE":
            # Create the filename to be inplaneprofile_depth_[number].csv
            filepaths.append(
                os.path.join(
                    output_directory,
                    "inplaneprofile_{0:d}mm_[{1:d}].csv".format(int(scan_depth[i]), i),
                )
            )

        elif curvetype == "CROSSPLANE_PROFILE":
            # Create the filename to be crossplaneprofile_depth_[number].csv
            filepaths.append(
                os.path.join(
                    output_directory,
                    "crossplaneprofile_{0:d}mm_[{1:d}].csv".format(
                        int(scan_depth[i]), i
                    ),
                )
            )

        else:
            # Raise an error if the curve type was not as expected
            raise ValueError("Unexpected scan_curvetype")

    return filepaths
