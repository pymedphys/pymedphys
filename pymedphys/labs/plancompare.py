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


"""Compare Mosaiq fields using MU Density
"""

import itertools

from pymedphys._imports import numpy as np

import matplotlib.pyplot as plt

import pymedphys


def plot_mu_densities(labels, mu_density_results):
    for label, results in zip(labels, mu_density_results):
        xx = results[0]
        yy = results[1]
        mu_density = results[2]
        plt.figure()
        plt.pcolormesh(xx, yy, mu_density)
        plt.colorbar()
        plt.title("MU density | {}".format(label))
        plt.xlabel("MLC direction (mm)")
        plt.ylabel("Jaw direction (mm)")
        plt.gca().invert_yaxis()


def plot_gantry_collimator(labels, deliveries):
    plt.figure()
    plt.title("Gantry Angle")
    for label, delivery_data in zip(labels, deliveries):
        plt.plot(
            delivery_data.monitor_units, delivery_data.gantry, label=label, alpha=0.5
        )
    plt.xlabel("Monitor Units")
    plt.ylabel("Gantry Angle")
    plt.legend()

    plt.figure()
    plt.title("Colimator Angle")
    for label, delivery_data in zip(labels, deliveries):
        plt.plot(
            delivery_data.monitor_units,
            delivery_data.collimator,
            label=label,
            alpha=0.5,
        )
    plt.xlabel("Monitor Units")
    plt.ylabel("Collimator Angle")
    plt.legend()


def compare_mosaiq_fields(servers, field_ids):
    unique_servers = list(set(servers))

    with pymedphys.mosaiq.connect(unique_servers) as cursors:
        deliveries = [
            pymedphys.Delivery.from_mosaiq(cursors[server], field_id)
            for server, field_id in zip(servers, field_ids)
        ]

    mu_density_results = [delivery_data.mudensity() for delivery_data in deliveries]

    mu_densities = [results[2] for results in mu_density_results]

    labels = [
        "Server: `{}` | Field ID: `{}`".format(server, field_id)
        for server, field_id in zip(servers, field_ids)
    ]

    plot_gantry_collimator(labels, deliveries)
    plot_mu_densities(labels, mu_density_results)

    mu_densities_match = np.all(
        [
            np.all(np.abs(mu_density_a - mu_density_b) < 0.1)
            for mu_density_a, mu_density_b in itertools.combinations(mu_densities, 2)
        ]
    )

    plt.show()
    print("MU Densities match: {}".format(mu_densities_match))

    return deliveries, mu_densities
