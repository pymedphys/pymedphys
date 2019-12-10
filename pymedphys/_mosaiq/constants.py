# Copyright (C) 2018 Cancer Care Associates

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

TOLERANCE_TYPES = {
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
