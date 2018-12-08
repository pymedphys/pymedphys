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


"""Compare fields using MU Density
"""

import itertools

import numpy as np
import matplotlib.pyplot as plt

from .._level1.typedeliverydata import get_delivery_parameters
from .._level1.msqconnect import multi_mosaiq_connect

from .._level2.mudensity import calc_mu_density
from .._level2.msqdelivery import delivery_data_from_mosaiq

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def mu_density_from_delivery_data(delivery_data):
    mu, mlc, jaw = get_delivery_parameters(delivery_data)
    xx, yy, mu_density = calc_mu_density(mu, mlc, jaw)

    return xx, yy, mu_density


def plot_mu_densities(labels, mu_density_results):
    for label, results in zip(labels, mu_density_results):
        xx = results[0]
        yy = results[1]
        mu_density = results[2]
        plt.figure()
        plt.pcolormesh(xx, yy, mu_density)
        plt.colorbar()
        plt.title('MU density | {}'.format(label))
        plt.xlabel('MLC direction (mm)')
        plt.ylabel('Jaw direction (mm)')
        plt.gca().invert_yaxis()


def plot_gantry_collimator(labels, deliveries):
    plt.figure()
    plt.title('Gantry Angle')
    for label, delivery_data in zip(labels, deliveries):
        plt.plot(
            delivery_data.monitor_units, delivery_data.gantry,
            label=label, alpha=0.5)
    plt.xlabel('Monitor Units')
    plt.ylabel('Gantry Angle')
    plt.legend()

    plt.figure()
    plt.title('Colimator Angle')
    for label, delivery_data in zip(labels, deliveries):
        plt.plot(
            delivery_data.monitor_units, delivery_data.collimator,
            label=label, alpha=0.5)
    plt.xlabel('Monitor Units')
    plt.ylabel('Collimator Angle')
    plt.legend()


def compare_mosaiq_fields(servers, field_ids):
    unique_servers = list(set(servers))

    with multi_mosaiq_connect(unique_servers) as cursors:
        deliveries = [
            delivery_data_from_mosaiq(cursors[server], field_id)
            for server, field_id in zip(servers, field_ids)
        ]

    mu_density_results = [
        mu_density_from_delivery_data(delivery_data)
        for delivery_data in deliveries
    ]

    mu_densities = [
        results[2]
        for results in mu_density_results
    ]

    labels = [
        "Server: `{}` | Field ID: `{}`".format(server, field_id)
        for server, field_id in zip(servers, field_ids)]

    plot_gantry_collimator(labels, deliveries)
    plot_mu_densities(labels, mu_density_results)

    mu_densities_match = np.all([
        np.all(np.abs(mu_density_a - mu_density_b) < 0.1)
        for mu_density_a, mu_density_b
        in itertools.combinations(mu_densities, 2)
    ])

    plt.show()
    print("MU Densities match: {}".format(mu_densities_match))

    return deliveries, mu_densities
