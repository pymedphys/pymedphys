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

import pydicom

from pymedphys_utilities.transforms import convert_IEC_angle_to_bipolar
from pymedphys_base.delivery import Delivery

from ..rtplan import (
    get_gantry_angles_from_dicom,
    build_control_points,
    replace_fraction_group,
    replace_beam_sequence,
    restore_trailing_zeros,
    merge_beam_sequences,
    get_fraction_group_index,
    convert_to_one_fraction_group,
    get_fraction_group_beam_sequence_and_meterset)

from .utilities import (
    jaw_dd2dcm,
    mlc_dd2dcm,
    angle_dd2dcm,
    gantry_tol_from_gantry_angles)


def load_dicom_file(filepath):
    dicom_dataset = pydicom.dcmread(filepath, force=True)
    return dicom_dataset


class DeliveryDicom(Delivery):
    @classmethod
    def load_all_fractions_from_file(cls, filepath):
        return cls.load_all_fractions(load_dicom_file(filepath))

    @classmethod
    def load_all_fractions(cls, dicom_dataset):
        fraction_group_numbers = tuple(
            fraction_group.FractionGroupNumber
            for fraction_group in dicom_dataset.FractionGroupSequence
        )

        all_fractions = {
            fraction_group_number: cls.from_dicom(
                dicom_dataset, fraction_group_number)
            for fraction_group_number in fraction_group_numbers
        }

        return all_fractions

    @classmethod
    def from_dicom_file(cls, filepath, fraction_group_number):
        return cls.from_dicom(
            load_dicom_file(filepath), fraction_group_number)

    @classmethod
    def from_dicom(cls, dicom_dataset, fraction_group_number):
        (
            beam_sequence, metersets
        ) = get_fraction_group_beam_sequence_and_meterset(
            dicom_dataset, fraction_group_number)

        delivery_data_by_beam_sequence = []
        for beam, meterset in zip(beam_sequence, metersets):
            delivery_data_by_beam_sequence.append(
                cls.from_dicom_beam(beam, meterset))

        return cls.combine(*delivery_data_by_beam_sequence)

    @classmethod
    def from_dicom_beam(cls, beam, meterset):
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

        return cls(mu, gantry_angles, collimator_angles, mlcs, jaw)

    def to_dicom(self, dicom_template, fraction_group_number=None):
        filtered = self.filter_cps()
        if fraction_group_number is None:
            fraction_group_number = self.fraction_group_number(dicom_template)

        single_fraction_group_template = convert_to_one_fraction_group(
            dicom_template, fraction_group_number)

        template_gantry_angles = get_gantry_angles_from_dicom(
            single_fraction_group_template)

        gantry_tol = gantry_tol_from_gantry_angles(template_gantry_angles)

        all_masked_delivery_data = filtered.mask_by_gantry(
            template_gantry_angles, gantry_tol)

        fraction_group_index = get_fraction_group_index(
            single_fraction_group_template, fraction_group_number)

        single_beam_dicoms = []
        for beam_index, masked_delivery_data in enumerate(all_masked_delivery_data):
            single_beam_dicoms.append(masked_delivery_data.to_dicom_beam(
                single_fraction_group_template, beam_index,
                fraction_group_index))

        return merge_beam_sequences(single_beam_dicoms)

    def to_dicom_beam(self, dicom_template,
                      beam_index, fraction_group_index):

        created_dicom = deepcopy(dicom_template)
        data_converted = self.coordinate_convert()

        beam = created_dicom.BeamSequence[beam_index]
        cp_sequence = beam.ControlPointSequence
        initial_cp = cp_sequence[0]
        subsequent_cp = cp_sequence[-1]

        all_control_points = build_control_points(
            initial_cp, subsequent_cp, data_converted)

        beam_meterset = '{0:.6f}'.format(data_converted['monitor_units'][-1])
        replace_fraction_group(
            created_dicom, beam_meterset, beam_index, fraction_group_index)
        replace_beam_sequence(created_dicom, all_control_points, beam_index)

        restore_trailing_zeros(created_dicom)

        return created_dicom

    def fraction_group_number(self, dicom_template, gantry_tol=3,
                              meterset_tol=0.5):
        filtered = self.filter_cps()
        fraction_groups = dicom_template.FractionGroupSequence

        if len(fraction_groups) == 1:
            return fraction_groups[0].FractionGroupNumber

        fraction_group_numbers = [
            fraction_group.FractionGroupNumber
            for fraction_group in fraction_groups
        ]

        dicom_metersets_by_fraction_group = [
            get_fraction_group_beam_sequence_and_meterset(
                dicom_template, fraction_group_number)[1]
            for fraction_group_number in fraction_group_numbers
        ]

        split_by_fraction_group = [
            convert_to_one_fraction_group(
                dicom_template, fraction_group_number)
            for fraction_group_number in fraction_group_numbers
        ]

        gantry_angles_by_fraction_group = [
            get_gantry_angles_from_dicom(dataset)
            for dataset in split_by_fraction_group]

        deliver_data_metersets_by_fraction_group = [
            filtered.metersets(gantry_angles, gantry_tol)
            for gantry_angles in gantry_angles_by_fraction_group
        ]

        maximum_deviations = []
        for dicom_metersets, delivery_data_metersets in zip(
                dicom_metersets_by_fraction_group,  # nopep8
                deliver_data_metersets_by_fraction_group):  # nopep8

            try:
                maximmum_diff = np.max(np.abs(
                    np.array(dicom_metersets) -
                    np.array(delivery_data_metersets)))
            except ValueError:
                maximmum_diff = np.inf

            maximum_deviations.append(maximmum_diff)

        deviations_within_tol = np.array(maximum_deviations) <= meterset_tol

        if np.sum(deviations_within_tol) < 1:
            raise ValueError(
                "A fraction group was not able to be found with the metersets "
                "and gantry angles defined by the tolerances provided. "
                "Please manually define the fraction group number.")

        if np.sum(deviations_within_tol) > 1:
            raise ValueError(
                "More than one fraction group was found that had metersets "
                "and gantry angles within the tolerances provided. "
                "Please manually define the fraction group number.")

        fraction_group_number = np.array(
            fraction_group_numbers)[deviations_within_tol]

        return fraction_group_number

    def coordinate_convert(self):
        monitor_units = self.monitor_units
        mlc = mlc_dd2dcm(self.mlc)
        jaw = jaw_dd2dcm(self.jaw)
        gantry_angle, gantry_movement = angle_dd2dcm(self.gantry)
        collimator_angle, collimator_movement = angle_dd2dcm(
            self.collimator)

        return {
            'monitor_units': monitor_units,
            'mlc': mlc,
            'jaw': jaw,
            'gantry_angle': gantry_angle,
            'gantry_movement': gantry_movement,
            'collimator_angle': collimator_angle,
            'collimator_movement': collimator_movement
        }
