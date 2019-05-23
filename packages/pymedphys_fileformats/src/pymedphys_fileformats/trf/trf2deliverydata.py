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

import numpy as np

from pymedphys_deliverydata.object import DeliveryData

from .constants import (
    GANTRY_NAME, COLLIMATOR_NAME,
    Y1_LEAF_BANK_NAMES, Y2_LEAF_BANK_NAMES,
    JAW_NAMES
)
from .trf2pandas import decode_trf


def delivery_data_from_logfile(logfile_path):
    logfile_dataframe = decode_trf(logfile_path)

    return delivery_data_from_pandas(logfile_dataframe)


def delivery_data_from_pandas(logfile_dataframe) -> DeliveryData:
    raw_monitor_units = logfile_dataframe[
        'Step Dose/Actual Value (Mu)'].values.tolist()

    diff = np.append([0], np.diff(raw_monitor_units))
    diff[diff < 0] = 0

    monitor_units = np.cumsum(diff).tolist()

    gantry = logfile_dataframe[GANTRY_NAME].values.tolist()
    collimator = logfile_dataframe[COLLIMATOR_NAME].values.tolist()

    y1_bank = [
        logfile_dataframe[name].values.tolist()
        for name in Y1_LEAF_BANK_NAMES
    ]

    y2_bank = [
        logfile_dataframe[name].values.tolist()
        for name in Y2_LEAF_BANK_NAMES
    ]

    mlc = [y1_bank, y2_bank]
    mlc = np.swapaxes(mlc, 0, 2)

    jaw = [
        logfile_dataframe[name].values.tolist()
        for name in JAW_NAMES
    ]
    jaw = np.swapaxes(jaw, 0, 1)

    logfile_delivery_data = DeliveryData(
        monitor_units, gantry, collimator, mlc, jaw
    )

    return logfile_delivery_data
