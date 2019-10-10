# Copyright (C) 2019 Cancer Care Associates

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


import pathlib
import re

from .mephysto import absolute_scans_from_mephysto


def load_and_normalise_mephysto(directory, regex, absolute_doses, normalisation_depth):
    """Read and normalise a directory of Mephysto files.

    Mephysto files are renormalised at the ``normalistation_depth`` to be
    equal to the values passed within the ``absolute_doses`` dictionary.

    Parameters
    ----------
    directory : path like object
        The directory containing the Mephysto files.
    regex : str
        A regex string defined such that ``re.match(regex, mcc_filename).group(1)``
        returns the key used to look up the absolute doses.
    absolute_doses : dict
        A dictionary mapping file keys to absolute doses defined at the
        ``normalisation_depth``.
    normalisation_depth : float
        The normalisation depth at which to apply the absolute doses.
        Can also optionally pass the string ``'dmax'``. This is in mm.

    Returns
    -------
    absolute_scans_per_field : dictionary
        A dictionary with the same keys as ``absolute_doses`` with the
        re-normalised depth doses and profiles contained within it.
    """
    directory = pathlib.Path(directory)

    all_mephysto_files = list(directory.glob("*.mcc"))
    matches = [re.match(regex, filepath.name) for filepath in all_mephysto_files]
    keys = [match.group(1) for match in matches if match]
    mephysto_files = [
        filepath for filepath, match in zip(all_mephysto_files, matches) if match
    ]

    if not set(keys).issubset(set(absolute_doses.keys())):
        keys_not_found = set(keys) - set(absolute_doses.keys())
        raise ValueError(
            "The following keys were not provided within the "
            f"`absolute_doses` variable:\n{keys_not_found}"
        )

    mephysto_file_map = dict(zip(keys, mephysto_files))

    absolute_scans_per_field = {
        key: absolute_scans_from_mephysto(
            mephysto_file_map[key], absolute_doses[key], normalisation_depth
        )
        for key in keys
    }

    return absolute_scans_per_field
