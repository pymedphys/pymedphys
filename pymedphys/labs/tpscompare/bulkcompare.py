# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
