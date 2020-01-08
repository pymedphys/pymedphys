# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Type

from pymedphys._imports import numpy as np

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
    def from_logfile(cls, filepath):
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
