# Copyright (C) 2020 Stuart Swerdloff, Matthew Jennings, Simon Biggs

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


def _get_vr_anonymous_hardcode_replacement_value(
    value_representation, current_value=None
):
    """A single dispatch function that is used for any VR with the current_value of the element ignored
    This is the default for the replacement strategy
    """
    return get_vr_anonymous_replacement_value_dict()[value_representation]


def _get_AE_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("AE", current_value)


def _get_AS_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("AS", current_value)


def _get_CS_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("CS", current_value)


def _get_DA_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("DA", current_value)


def _get_DS_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("DS", current_value)


def _get_DT_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("DT", current_value)


def _get_LO_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("LO", current_value)


def _get_LT_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("LT", current_value)


def _get_OB_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("OB", current_value)


def _get_OB_or_OW_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("OB or OW", current_value)


def _get_OW_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("OW", current_value)


def _get_PN_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("PN", current_value)


def _get_SH_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("SH", current_value)


def _get_SQ_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("SQ", current_value)


def _get_ST_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("ST", current_value)


def _get_TM_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("TM", current_value)


def _get_UI_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("UI", current_value)


def _get_US_anonymous_hardcode_replacement_value(current_value):
    return _get_vr_anonymous_hardcode_replacement_value("US", current_value)


ANONYMISATION_HARDCODE_DISPATCH = dict(
    {
        "AE": _get_AE_anonymous_hardcode_replacement_value,
        "AS": _get_AS_anonymous_hardcode_replacement_value,
        "CS": _get_CS_anonymous_hardcode_replacement_value,
        "DA": _get_DA_anonymous_hardcode_replacement_value,
        "DS": _get_DS_anonymous_hardcode_replacement_value,
        "DT": _get_DT_anonymous_hardcode_replacement_value,
        "LO": _get_LO_anonymous_hardcode_replacement_value,
        "LT": _get_LT_anonymous_hardcode_replacement_value,
        "OB": _get_OB_anonymous_hardcode_replacement_value,
        "OB or OW": _get_OB_or_OW_anonymous_hardcode_replacement_value,
        "OW": _get_OW_anonymous_hardcode_replacement_value,
        "PN": _get_PN_anonymous_hardcode_replacement_value,
        "SH": _get_SH_anonymous_hardcode_replacement_value,
        "SQ": _get_SQ_anonymous_hardcode_replacement_value,
        "ST": _get_ST_anonymous_hardcode_replacement_value,
        "TM": _get_TM_anonymous_hardcode_replacement_value,
        "UI": _get_UI_anonymous_hardcode_replacement_value,
        "US": _get_US_anonymous_hardcode_replacement_value,
    }
)
