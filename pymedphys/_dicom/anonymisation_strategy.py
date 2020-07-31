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

from pymedphys._dicom.constants import PYMEDPHYS_ROOT_UID


@functools.lru_cache(maxsize=1)
def get_vr_anonymous_replacement_value_dict():
    VR_ANONYMOUS_REPLACEMENT_VALUE_DICT = {
        "AE": "Anonymous",
        "AS": "100Y",
        "CS": "ANON",
        "DA": "20190303",
        "DS": "12345678.9",
        "DT": "20190303000900.000000",
        "LO": "Anonymous",
        "LT": "Anonymous",
        "OB": (0).to_bytes(2, "little"),
        "OB or OW": (0).to_bytes(2, "little"),
        "OW": (0).to_bytes(2, "little"),
        "PN": "Anonymous",
        "SH": "Anonymous",
        "SQ": [pydicom.Dataset()],
        "ST": "Anonymous",
        "TM": "000900.000000",
        "UI": PYMEDPHYS_ROOT_UID,
        "US": 12345,
    }

    return VR_ANONYMOUS_REPLACEMENT_VALUE_DICT


def _get_vr_anonymous_hardcode_replacement_value(current_value, value_representation):
    """A single dispatch function that is used for any VR with the current_value of the element ignored
    This is the default for the replacement strategy
    """
    if current_value is None:
        logging.debug("Replacing empty value with hardcoded anonymisation value")

    return get_vr_anonymous_replacement_value_dict()[value_representation]


@functools.lru_cache(maxsize=1)
def get_default_hardcode_dispatch():
    ANONYMISATION_HARDCODE_DISPATCH = {
        key: functools.partial(
            _get_vr_anonymous_hardcode_replacement_value, value_representation=key
        )
        for key in get_vr_anonymous_replacement_value_dict().keys()
    }
    return ANONYMISATION_HARDCODE_DISPATCH
