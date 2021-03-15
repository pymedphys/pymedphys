# Copyright (C) 2020 Jacob Rembish

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

TOLERANCE_TYPES = {
    0: "Unspecified",
    1: "Standard",
    2: "Hexapod",
    3: "electrons",
    4: "IMRT",
    5: "zz-breast",
    6: "Large Pt",
    7: "zz-CSA/Spine",
    8: "zz-Peacock",
    9: "zz-SRS/SBRT",
    10: "Zero Tolerance",
    11: "zz-Installer",
    12: "Novalis",
    13: "CBCT",
    14: "zz-Brain and HN",
    15: "Vault 6HD Table",
    16: "Vault 6HD Maximum",
    17: "zz-Exactrac",
    18: "Vault 2HD Table",
    19: "Vault 2HD Maximum",
    20: "Vault 4HD Table",
    21: "Vault 4HD Maximum",
}

SITE_CONSTANTS = {
    0: "Unknown",
    1: "VOID",
    2: "CLOSE",
    3: "COMPLETE",
    4: "HOLD",
    5: "APPROVE",
    6: "PROCESS_LOCK",
    7: "PENDING",
}

ENERGY_ENUM = {0: "Unspecified", 1: "KV", 2: "MV", 3: "MEV"}

MODALITY_ENUM = {
    0: "Unspecified",
    1: "X-rays",
    2: "Electrons",
    3: "Co-60",
    4: "Ortho",
    5: "E H/D",
    6: "Protons",
    7: "kV (orthovoltage)",
    8: "Ir-192",
    9: "Ion",
    20: "UserDefined",
}

METERSET_UNITS = {
    0: "Unspecified",
    1: "MU (Monitor Unit)",
    2: "MAMPSEC (MilliAmp Seconds)",
    3: "MP (Mega-Particles)",
    4: "Minutes",
    5: "Seconds",
}

TERMINATION_STATUS = {0: "Unknown", 1: "Normal", 2: "Operator", 3: "Machine"}

TERMINATION_VERIFY = {
    0: "Unspecified",
    1: "Verified",
    2: "Verified, override",
    3: "Not Verified",
}

FIELD_TYPES = {
    0: "Unspecified",
    1: "Static",
    2: "StepNShoot",
    3: "Setup",
    4: "kV Setup",
    5: "CT",
    6: "Port",
    7: "Fixed",
    8: "Dynamic",
    9: "MV CT",
    11: "Arc",
    12: "Skip Arcs",
    13: "VMAT",
    14: "DMLC",
    15: "Helical",
    16: "Fixed Angle",
    17: "Path",
    18: "Shot",
    20: "User Defined",
    21: "PDR",
}

ORIENTATION = {
    0: "Unknown",
    1: "HFS",
    2: "HFP",
    3: "HFDL",
    4: "HFDR",
    5: "FFS",
    6: "FFP",
    7: "FFDL",
    8: "FFDR",
    9: "SITTING",
}

IMAGE_APPROVAL = {
    0: "Rejected",
    1: "Approved",
    2: "Incomplete",
    3: "Not Required",
}
