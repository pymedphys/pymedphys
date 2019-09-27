# Copyright (C) 2017 Cancer Care Associates

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


import os

import numpy as np
import pandas as pd


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
    """Determine a useful filepath for the saving of each mephysto scan.
    """
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
            raise Exception("Unexpected scan_curvetype")

    return filepaths
