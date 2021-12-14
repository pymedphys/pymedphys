# Copyright (C) 2020 Stuart Swerdloff, Simon Biggs
# Copyright (C) 2018 Matthew Jennings, Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import logging

from pymedphys._imports import pydicom

from pymedphys._dicom.uid import PYMEDPHYS_ROOT_UID

REPLACEMENT_TO_VR_MAP = {
    "Anonymous": ["AE", "LO", "LT", "PN", "SH", "ST"],
    "100Y": ["AS"],
    "ANON": ["CS"],
    "20190303": ["DA"],
    "12345678.9": ["DS"],
    "20190303000900.000000": ["DT"],
    (0).to_bytes(2, "little"): ["OB", "OB or OW", "OW"],
    "000900.000000": ["TM"],
    PYMEDPHYS_ROOT_UID: ["UI"],
    12345: ["US"],
}

VR_TO_REPLACEMENT_MAP = {}
for value, keys in REPLACEMENT_TO_VR_MAP.items():
    for key in keys:
        VR_TO_REPLACEMENT_MAP[key] = value


def _get_vr_anonymous_hardcode_replacement_value(current_value, value_representation):
    """A single dispatch function that is used for any VR with the current_value of the element ignored
    This is the default for the replacement strategy
    """
    if current_value is None:
        # TODO: Decide if we actually want to be doing this. I haven't
        # been the biggest fan of this outcome.
        logging.debug("Replacing empty value with hardcoded anonymisation value")

    if value_representation == "SQ":
        # This is defined in here instead of within REPLACEMENT_TO_VR_MAP so that
        # pydicom does not get called during library import. This is to support
        # running other parts of pymedphys in environments where pydicom is not
        # installed.
        return [pydicom.Dataset()]

    return VR_TO_REPLACEMENT_MAP[value_representation]


_keys = list(VR_TO_REPLACEMENT_MAP.keys())
_keys.append("SQ")

ANONYMISATION_HARDCODE_DISPATCH = {
    key: functools.partial(
        _get_vr_anonymous_hardcode_replacement_value, value_representation=key
    )
    for key in _keys
}
