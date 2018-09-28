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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Compare fields using MU Density
"""

import itertools

import numpy as np
import matplotlib.pyplot as plt

from ..level1.msqconnect import multi_mosaiq_connect
from ..level1.mudensity import calc_mu_density
from ..level1.deliverydata import get_delivery_parameters
from ..level2.msqdelivery import delivery_data_from_mosaiq


def mu_density_from_delivery_data(delivery_data):
    mu, mlc, jaw = get_delivery_parameters(delivery_data)
    _, _, mu_density = calc_mu_density(mu, mlc, jaw)

    return mu_density


def plot_mu_densities(mu_densities):
    for mu_density in mu_densities:
        plt.figure()
        plt.pcolormesh(mu_density)
        plt.colorbar()
        plt.title('MU density')
        plt.xlabel('MLC direction (mm)')
        plt.ylabel('Jaw direction (mm)')
        plt.gca().invert_yaxis()


def mosaiq_fields_agree(servers, field_ids, plots=False):
    unique_servers = list(set(servers))

    with multi_mosaiq_connect(unique_servers) as cursors:
        deliveries = [
            delivery_data_from_mosaiq(cursors[server], field_id)
            for server, field_id in zip(servers, field_ids)
        ]

    mu_densities = [
        mu_density_from_delivery_data(delivery_data)
        for delivery_data in deliveries
    ]

    if plots:
        plot_mu_densities(mu_densities)

    return np.all([
        np.all(np.abs(mu_density_a - mu_density_b) < 0.1)
        for mu_density_a, mu_density_b
        in itertools.combinations(mu_densities, 2)
    ])
