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


"""Compare Mosaiq fields using MetersetMap
"""

import itertools

from pymedphys._imports import numpy as np

import matplotlib.pyplot as plt

import pymedphys


def plot_metersetmaps(labels, metersetmap_results):
    for label, results in zip(labels, metersetmap_results):
        xx = results[0]
        yy = results[1]
        metersetmap = results[2]
        plt.figure()
        plt.pcolormesh(xx, yy, metersetmap)
        plt.colorbar()
        plt.title("MetersetMap | {}".format(label))
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
    plt.title("Collimator Angle")
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

    metersetmap_results = [delivery_data.metersetmap() for delivery_data in deliveries]

    metersetmaps = [results[2] for results in metersetmap_results]

    labels = [
        "Server: `{}` | Field ID: `{}`".format(server, field_id)
        for server, field_id in zip(servers, field_ids)
    ]

    plot_gantry_collimator(labels, deliveries)
    plot_metersetmaps(labels, metersetmap_results)

    metersetmaps_match = np.all(
        [
            np.all(np.abs(metersetmap_a - metersetmap_b) < 0.1)
            for metersetmap_a, metersetmap_b in itertools.combinations(metersetmaps, 2)
        ]
    )

    plt.show()
    print("MetersetMaps match: {}".format(metersetmaps_match))

    return deliveries, metersetmaps
