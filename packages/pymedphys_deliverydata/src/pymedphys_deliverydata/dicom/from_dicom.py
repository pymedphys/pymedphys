# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

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


from copy import deepcopy

import numpy as np

from pymedphys_base.deliverydata import DeliveryDataBase
from pymedphys_utilities.transforms import convert_IEC_angle_to_bipolar
from pymedphys_dicom.rtplan import (
    get_fraction_group_beam_sequence_and_meterset)

from ..utilities import merge_delivery_data


def delivery_data_from_dicom(dicom_dataset, fraction_group_number) -> DeliveryDataBase:
    (
        beam_sequence, metersets
    ) = get_fraction_group_beam_sequence_and_meterset(
        dicom_dataset, fraction_group_number)

    delivery_data_by_beam_sequence = []
    for beam, meterset in zip(beam_sequence, metersets):
        delivery_data_by_beam_sequence.append(
            delivery_data_from_dicom_single_beam(beam, meterset))

    return merge_delivery_data(delivery_data_by_beam_sequence)


def delivery_data_from_dicom_single_beam(beam, meterset):
    leaf_boundaries = beam.BeamLimitingDeviceSequence[-1].LeafPositionBoundaries
    leaf_widths = np.diff(leaf_boundaries)

    assert beam.BeamLimitingDeviceSequence[-1].NumberOfLeafJawPairs == len(
        leaf_widths)
    num_leaves = len(leaf_widths)

    control_points = beam.ControlPointSequence

    mlcs = [
        control_point.BeamLimitingDevicePositionSequence[-1].LeafJawPositions
        for control_point in control_points
    ]

    mlcs = [
        np.array([
            -np.array(mlc[0:num_leaves][::-1]),  # pylint: disable=invalid-unary-operand-type  # nopep8
            np.array(mlc[num_leaves::][::-1])
        ][::-1]).T
        for mlc in mlcs
    ]

    dicom_jaw = [
        control_point.BeamLimitingDevicePositionSequence[0].LeafJawPositions
        for control_point in control_points
    ]

    jaw = np.array(dicom_jaw)

    second_col = deepcopy(jaw[:, 1])
    jaw[:, 1] = jaw[:, 0]
    jaw[:, 0] = second_col

    jaw[:, 1] = -jaw[:, 1]

    final_mu_weight = np.array(beam.FinalCumulativeMetersetWeight)

    mu = [
        meterset *
        np.array(control_point.CumulativeMetersetWeight) / final_mu_weight
        for control_point in control_points
    ]

    gantry_angles = convert_IEC_angle_to_bipolar([
        control_point.GantryAngle
        for control_point in control_points
    ])

    collimator_angles = convert_IEC_angle_to_bipolar([
        control_point.BeamLimitingDeviceAngle
        for control_point in control_points
    ])

    return DeliveryDataBase(mu, gantry_angles, collimator_angles, mlcs, jaw)
