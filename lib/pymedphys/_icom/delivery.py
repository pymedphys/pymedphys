# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np

import pymedphys._base.delivery

from . import extract


def get_delivery_data_items(single_icom_stream):
    shrunk_stream, mu = extract.extract(single_icom_stream, "Delivery MU")
    shrunk_stream, gantry = extract.extract(shrunk_stream, "Gantry")
    shrunk_stream, collimator = extract.extract(shrunk_stream, "Collimator")

    shrunk_stream, mlc = extract.extract_coll(shrunk_stream, b"MLCX", 160)
    mlc = np.array(mlc)
    mlc = mlc.reshape((80, 2))
    mlc = np.fliplr(np.flipud(mlc * 10))
    mlc[:, 1] = -mlc[:, 1]
    mlc = np.round(mlc, 10)

    shrunk_stream, jaw = extract.extract_coll(shrunk_stream, b"ASYMY", 2)
    jaw = np.round(np.array(jaw) * 10, 10)
    jaw = np.flipud(jaw)

    return mu, gantry, collimator, mlc, jaw


def delivery_from_icom_stream(icom_stream):
    icom_stream_points = extract.get_data_points(icom_stream)
    delivery_raw = [
        get_delivery_data_items(single_icom_stream)
        for single_icom_stream in icom_stream_points
    ]

    mu = np.array([item[0] for item in delivery_raw])
    diff_mu = np.concatenate([[0], np.diff(mu)])
    diff_mu[diff_mu < 0] = 0
    mu = np.cumsum(diff_mu)

    gantry = np.array([item[1] for item in delivery_raw])
    collimator = np.array([item[2] for item in delivery_raw])
    mlc = np.array([item[3] for item in delivery_raw])
    jaw = np.array([item[4] for item in delivery_raw])

    return mu, gantry, collimator, mlc, jaw


class DeliveryIcom(
    pymedphys._base.delivery.DeliveryBase  # pylint: disable = protected-access
):
    @classmethod
    def from_icom(cls, icom_stream):
        return cls(  # pylint: disable = protected-access
            *delivery_from_icom_stream(icom_stream)
        )._filter_cps()
