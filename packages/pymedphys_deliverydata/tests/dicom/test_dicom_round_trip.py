# Copyright (C) 2019 Simon Biggs and Cancer Care Associates

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


import os

import pytest

import numpy as np
import matplotlib.pyplot as plt

import pydicom

from pymedphys_utilities.algorithms import maintain_order_unique

from pymedphys_dicom.rtplan import (
    get_metersets_from_dicom,
    get_gantry_angles_from_dicom)

from pymedphys.deliverydata import DeliveryData

# pylint: disable=redefined-outer-name


DIR_TO_TEST_MAP = {
    "original": {
        'fraction_group': 1
    },
    "multi_fraction_groups": {
        'fraction_group': 2
    }
}

DIR_TO_TEST = 'multi_fraction_groups'
FRACTION_GROUP = DIR_TO_TEST_MAP[DIR_TO_TEST]['fraction_group']

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "data", DIR_TO_TEST)
DICOM_FILEPATH = os.path.abspath(os.path.join(
    DATA_DIRECTORY, "rtplan.dcm"))
LOGFILE_FILEPATH = os.path.abspath(os.path.join(
    DATA_DIRECTORY, "imrt.trf"))


@pytest.fixture
def loaded_dicom_dataset():
    return pydicom.dcmread(DICOM_FILEPATH, force=True)


@pytest.fixture
def logfile_delivery_data() -> DeliveryData:
    return DeliveryData.from_logfile(LOGFILE_FILEPATH)


@pytest.fixture
def loaded_dicom_gantry_angles(loaded_dicom_dataset):
    return get_gantry_angles_from_dicom(loaded_dicom_dataset)


def test_round_trip_dd2dcm2dd(loaded_dicom_dataset,
                              logfile_delivery_data: DeliveryData):
    original = logfile_delivery_data.filter_cps()
    template = loaded_dicom_dataset

    dicom = original.to_dicom(template)
    processed = DeliveryData.from_dicom(dicom, FRACTION_GROUP)

    assert np.all(
        np.around(original.monitor_units, 2) ==
        np.around(processed.monitor_units, 2))

    assert np.all(
        np.around(original.gantry, 2) ==
        np.around(processed.gantry, 2))

    assert np.all(
        np.around(original.mlc, 2) ==
        np.around(processed.mlc, 2))

    assert np.all(
        np.around(original.jaw, 2) ==
        np.around(processed.jaw, 2))

    # Collimator not currently handled appropriately
    assert np.all(
        np.around(original.collimator, 2) ==
        np.around(processed.collimator, 2))


def test_round_trip_dcm2dd2dcm(loaded_dicom_dataset,
                               loaded_dicom_gantry_angles):
    original = loaded_dicom_dataset
    original_gantry_angles = loaded_dicom_gantry_angles

    delivery_data = DeliveryData.from_dicom(original, FRACTION_GROUP)
    processed = delivery_data.to_dicom(original)

    assert (
        num_of_control_points(original) == num_of_control_points(processed)
    )

    assert (
        maintain_order_unique(delivery_data.gantry) == original_gantry_angles)

    processed_gantry_angles = get_gantry_angles_from_dicom(processed)

    assert original_gantry_angles == processed_gantry_angles

    assert (
        source_to_surface_distances(original) ==
        source_to_surface_distances(processed))

    assert first_mlc_positions(original) == first_mlc_positions(processed)

    assert str(original) == str(processed)


def test_get_metersets_from_delivery_data(logfile_delivery_data,
                                          loaded_dicom_dataset,
                                          loaded_dicom_gantry_angles):
    gantry_tol = 3
    expected = get_metersets_from_dicom(loaded_dicom_dataset, FRACTION_GROUP)

    filtered = logfile_delivery_data.filter_cps()
    metersets = filtered.metersets(loaded_dicom_gantry_angles, gantry_tol)

    try:
        assert np.all(np.abs(np.array(expected) - np.array(metersets)) <= 0.2)
    except AssertionError:
        print("\nIn DICOM file:\n   {}".format(expected))
        print("\nIn log file:\n   {}".format(metersets))
        raise


def test_mudensity_agreement(loaded_dicom_dataset, logfile_delivery_data):
    dicom_delivery_data = DeliveryData.from_dicom(
        loaded_dicom_dataset, FRACTION_GROUP)

    dicom_mu_density = dicom_delivery_data.mudensity(grid_resolution=5)
    logfile_mu_density = logfile_delivery_data.mudensity(grid_resolution=5)

    diff = logfile_mu_density - dicom_mu_density
    max_diff = np.max(np.abs(diff))
    std_diff = np.std(diff)
    try:
        assert max_diff < 4.1
        assert std_diff < 0.4
    except AssertionError:
        max_val = np.max([
            np.max(logfile_mu_density),
            np.max(dicom_mu_density)
        ])

        plt.figure()
        plt.pcolormesh(dicom_mu_density, vmin=0, vmax=max_val)
        plt.colorbar()

        plt.figure()
        plt.pcolormesh(logfile_mu_density, vmin=0, vmax=max_val)
        plt.colorbar()

        plt.figure()
        plt.pcolormesh(
            logfile_mu_density - dicom_mu_density,
            vmin=-max_diff, vmax=max_diff, cmap='bwr')
        plt.colorbar()
        plt.show()
        raise


def num_of_control_points(dicom_dataset):
    return [
        len(beam.ControlPointSequence)
        for beam in dicom_dataset.BeamSequence
    ]


def source_to_surface_distances(dicom_dataset):
    SSDs = [
        {
            control_point.SourceToSurfaceDistance
            for control_point in beam_sequence.ControlPointSequence
        }
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    return SSDs


def first_mlc_positions(dicom_dataset):
    result = [
        beam_sequence.ControlPointSequence[0].BeamLimitingDevicePositionSequence[1].LeafJawPositions
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    return result
