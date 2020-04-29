# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from copy import deepcopy

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._base.delivery import DeliveryBase
from pymedphys._utilities.transforms import convert_IEC_angle_to_bipolar

from ..rtplan import (
    build_control_points,
    convert_to_one_fraction_group,
    get_cp_attribute_leaning_on_prior,
    get_fraction_group_beam_sequence_and_meterset,
    get_fraction_group_index,
    get_gantry_angles_from_dicom,
    merge_beam_sequences,
    replace_beam_sequence,
    replace_fraction_group,
    restore_trailing_zeros,
)
from .utilities import (
    angle_dd2dcm,
    gantry_tol_from_gantry_angles,
    jaw_dd2dcm,
    mlc_dd2dcm,
)


def load_dicom_file(filepath):
    dicom_dataset = pydicom.dcmread(filepath, force=True, stop_before_pixels=True)
    return dicom_dataset


class DeliveryDicom(DeliveryBase):
    @classmethod
    def from_dicom(cls, dicom_dataset, fraction_number=None):

        if str(fraction_number).lower() == "all":
            return cls._load_all_fractions(dicom_dataset)

        if fraction_number is None:
            fractions = dicom_dataset.FractionGroupSequence
            fraction_numbers = [fraction.FractionGroupNumber for fraction in fractions]

            if len(fraction_numbers) == 1:
                fraction_number = fraction_numbers[0]
            else:
                raise ValueError(
                    "There is more than one fraction in this DICOM plan, please provide"
                    " the `fraction_number` parameter to define which one to pull.\n"
                    f"   Fraction numbers to choose from are: {fraction_numbers}"
                )

        beam_sequence, metersets = get_fraction_group_beam_sequence_and_meterset(
            dicom_dataset, fraction_number
        )

        delivery_data_by_beam_sequence = []
        for beam, meterset in zip(beam_sequence, metersets):
            delivery_data_by_beam_sequence.append(cls._from_dicom_beam(beam, meterset))

        return cls.combine(*delivery_data_by_beam_sequence)

    def to_dicom(self, dicom_template, fraction_number=None):
        filtered = self._filter_cps()
        if fraction_number is None:
            fraction_number = self._fraction_number(dicom_template)

        single_fraction_template = convert_to_one_fraction_group(
            dicom_template, fraction_number
        )

        template_gantry_angles = get_gantry_angles_from_dicom(single_fraction_template)

        gantry_tol = gantry_tol_from_gantry_angles(template_gantry_angles)

        all_masked_delivery_data = filtered._mask_by_gantry(  # pylint: disable = protected-access
            template_gantry_angles, gantry_tol
        )

        fraction_index = get_fraction_group_index(
            single_fraction_template, fraction_number
        )

        single_beam_dicoms = []
        for beam_index, masked_delivery_data in enumerate(all_masked_delivery_data):
            single_beam_dicoms.append(
                masked_delivery_data._to_dicom_beam(  # pylint: disable = protected-access
                    single_fraction_template, beam_index, fraction_index
                )
            )

        return merge_beam_sequences(single_beam_dicoms)

    @classmethod
    def _load_all_fractions_from_file(cls, filepath):
        return cls._load_all_fractions(load_dicom_file(filepath))

    @classmethod
    def _load_all_fractions(cls, dicom_dataset):
        fraction_numbers = tuple(
            fraction.FractionGroupNumber
            for fraction in dicom_dataset.FractionGroupSequence
        )

        all_fractions = {
            fraction_number: cls.from_dicom(dicom_dataset, fraction_number)
            for fraction_number in fraction_numbers
        }

        return all_fractions

    @classmethod
    def _from_dicom_file(cls, filepath, fraction_number):
        return cls.from_dicom(load_dicom_file(filepath), fraction_number)

    @classmethod
    def _from_dicom_beam(cls, beam, meterset):
        if meterset is None:
            raise ValueError("Meterset should not ever be None")

        leaf_boundaries = beam.BeamLimitingDeviceSequence[-1].LeafPositionBoundaries
        leaf_widths = np.diff(leaf_boundaries)

        assert beam.BeamLimitingDeviceSequence[-1].NumberOfLeafJawPairs == len(
            leaf_widths
        )
        num_leaves = len(leaf_widths)

        control_points = beam.ControlPointSequence

        beam_limiting_device_position_sequences = get_cp_attribute_leaning_on_prior(
            control_points, "BeamLimitingDevicePositionSequence"
        )

        mlcs = [
            sequence[-1].LeafJawPositions
            for sequence in beam_limiting_device_position_sequences
        ]

        mlcs = [
            np.array(
                [-np.array(mlc[0:num_leaves][::-1]), np.array(mlc[num_leaves::][::-1])][
                    ::-1
                ]
            ).T
            for mlc in mlcs
        ]

        dicom_jaw = [
            sequence[0].LeafJawPositions
            for sequence in beam_limiting_device_position_sequences
        ]

        jaw = np.array(dicom_jaw)

        second_col = deepcopy(jaw[:, 1])
        jaw[:, 1] = jaw[:, 0]
        jaw[:, 0] = second_col

        jaw[:, 1] = -jaw[:, 1]

        final_mu_weight = np.array(beam.FinalCumulativeMetersetWeight)

        if final_mu_weight is None:
            raise ValueError("FinalCumulativeMetersetWeight should not be None")

        # https://dicom.innolitics.com/ciods/rt-plan/rt-beams/300a00b0/300a0111/300a0134
        # http://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.8.14.html#sect_C.8.8.14.1

        cumulative_meterset_weight = [
            control_point.CumulativeMetersetWeight for control_point in control_points
        ]

        for weight in cumulative_meterset_weight:
            if weight is None:
                raise ValueError(
                    "Cumulative Meterset weight not set within DICOM RT plan file. "
                    "This may be due to the plan being exported from a planning system "
                    "without the dose being calculated."
                )

        mu = [
            meterset * np.array(weight) / final_mu_weight
            for control_point, weight in zip(control_points, cumulative_meterset_weight)
        ]

        gantry_angles = convert_IEC_angle_to_bipolar(
            get_cp_attribute_leaning_on_prior(control_points, "GantryAngle")
        )

        collimator_angles = convert_IEC_angle_to_bipolar(
            get_cp_attribute_leaning_on_prior(control_points, "BeamLimitingDeviceAngle")
        )

        return cls(mu, gantry_angles, collimator_angles, mlcs, jaw)

    def _to_dicom_beam(self, dicom_template, beam_index, fraction_index):

        created_dicom = deepcopy(dicom_template)
        data_converted = self._coordinate_convert()

        beam = created_dicom.BeamSequence[beam_index]
        cp_sequence = beam.ControlPointSequence
        initial_cp = cp_sequence[0]
        subsequent_cp = cp_sequence[-1]

        all_control_points = build_control_points(
            initial_cp, subsequent_cp, data_converted
        )

        beam_meterset = "{0:.6f}".format(data_converted["monitor_units"][-1])
        replace_fraction_group(created_dicom, beam_meterset, beam_index, fraction_index)
        replace_beam_sequence(created_dicom, all_control_points, beam_index)

        restore_trailing_zeros(created_dicom)

        return created_dicom

    def _matches_fraction(
        self, dicom_dataset, fraction_number, gantry_tol=3, meterset_tol=0.5
    ):
        filtered = self._filter_cps()
        dicom_metersets = get_fraction_group_beam_sequence_and_meterset(
            dicom_dataset, fraction_number
        )[1]

        dicom_fraction = convert_to_one_fraction_group(dicom_dataset, fraction_number)

        gantry_angles = get_gantry_angles_from_dicom(dicom_fraction)

        delivery_metersets = filtered._metersets(  # pylint: disable = protected-access
            gantry_angles, gantry_tol
        )

        try:
            maximmum_diff = np.max(
                np.abs(np.array(dicom_metersets) - np.array(delivery_metersets))
            )
        except ValueError:
            maximmum_diff = np.inf

        return maximmum_diff <= meterset_tol

    def _fraction_number(self, dicom_template, gantry_tol=3, meterset_tol=0.5):
        fractions = dicom_template.FractionGroupSequence

        if len(fractions) == 1:
            return fractions[0].FractionGroupNumber

        fraction_numbers = [fraction.FractionGroupNumber for fraction in fractions]

        fraction_matches = np.array(
            [
                self._matches_fraction(
                    dicom_template,
                    fraction_number,
                    gantry_tol=gantry_tol,
                    meterset_tol=meterset_tol,
                )
                for fraction_number in fraction_numbers
            ]
        )

        if np.sum(fraction_matches) < 1:
            raise ValueError(
                "A fraction group was not able to be found with the metersets "
                "and gantry angles defined by the tolerances provided. "
                "Please manually define the fraction group number."
            )

        if np.sum(fraction_matches) > 1:
            raise ValueError(
                "More than one fraction group was found that had metersets "
                "and gantry angles within the tolerances provided. "
                "Please manually define the fraction group number."
            )

        fraction_number = np.array(fraction_numbers)[fraction_matches]

        return fraction_number

    def _coordinate_convert(self):
        monitor_units = self.monitor_units
        mlc = mlc_dd2dcm(self.mlc)
        jaw = jaw_dd2dcm(self.jaw)
        gantry_angle, gantry_movement = angle_dd2dcm(self.gantry)
        collimator_angle, collimator_movement = angle_dd2dcm(self.collimator)

        return {
            "monitor_units": monitor_units,
            "mlc": mlc,
            "jaw": jaw,
            "gantry_angle": gantry_angle,
            "gantry_movement": gantry_movement,
            "collimator_angle": collimator_angle,
            "collimator_movement": collimator_movement,
        }
