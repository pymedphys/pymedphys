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

from __future__ import annotations

from typing import Type

import numpy as np

from pymedphys._base.delivery import DeliveryBase, DeliveryGeneric

from .constants import (
    COLLIMATOR_NAME,
    GANTRY_NAME,
    JAW_NAMES,
    Y1_LEAF_BANK_NAMES,
    Y2_LEAF_BANK_NAMES,
)
from .trf2pandas import read_trf


class DeliveryLogfile(DeliveryBase):
    @classmethod
    def from_logfile(cls, filepath) -> DeliveryLogfile:
        _, dataframe = read_trf(filepath)

        return cls._from_pandas(dataframe)

    @classmethod
    def _from_pandas(cls: Type[DeliveryGeneric], table) -> DeliveryGeneric:
        raw_monitor_units = table["Step Dose/Actual Value (Mu)"]

        diff = np.append([0], np.diff(raw_monitor_units))
        diff[diff < 0] = 0

        monitor_units = np.cumsum(diff)

        gantry = table[GANTRY_NAME]
        collimator = table[COLLIMATOR_NAME]

        y1_bank = [table[name] for name in Y1_LEAF_BANK_NAMES]

        y2_bank = [table[name] for name in Y2_LEAF_BANK_NAMES]

        mlc = [y1_bank, y2_bank]
        mlc = np.swapaxes(mlc, 0, 2)

        jaw = [table[name] for name in JAW_NAMES]
        jaw = np.swapaxes(jaw, 0, 1)

        return cls(monitor_units, gantry, collimator, mlc, jaw)
