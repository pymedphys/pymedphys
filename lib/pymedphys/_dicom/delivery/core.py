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

import os
import textwrap
from copy import deepcopy
from typing import Union, cast

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._base.delivery import DeliveryBase
from pymedphys._dicom import rtplan as _pmp_rtplan
from pymedphys._dicom.delivery import utilities
from pymedphys._utilities.transforms import convert_IEC_angle_to_bipolar

dicom_path_or_dataset = Union[os.PathLike, "pydicom.Dataset", str]


def _load_dicom_file(filepath: os.PathLike) -> "pydicom.Dataset":
    dicom_dataset = pydicom.dcmread(filepath, force=True, stop_before_pixels=True)

    return dicom_dataset


def _pretty_print(string):
    sections = textwrap.dedent(string).split("\n\n")
    wrapped = ["\n".join(textwrap.wrap(section)) for section in sections]

    return "\n\n".join(wrapped)


def _check_for_supported_collimation_device(
    beam_limiting_device_sequence: "pydicom.Sequence",
):
    """Validate whether or not the beam limiting devices in use are
    supported for use by ``pymedphys.Delivery.from_dicom``.

    Parameters
    ----------
    beam_limiting_device_sequence
        The ``BeamLimitingDeviceSequence`` from within a single item
        within the ``BeamSequence`` of an RT Plan DICOM dataset.

    Raises
    ------
    ValueError
        If the device types are not contained within the supported
        configrations.

    """
    rt_beam_limiting_device_types = {
        item.RTBeamLimitingDeviceType for item in beam_limiting_device_sequence
    }

    supported_configurations = [{"MLCX", "ASYMY"}]

    if not rt_beam_limiting_device_types in supported_configurations:
        raise ValueError(
            _pretty_print(
                """\
                    Currently only DICOM files where the beam
                    limiting devices consist of one of the following
                    combinations are supported:

                    * {supported_configurations}

                    The provided RT Plan DICOM file has the
                    following:

                        {rt_beam_limiting_device_types}

                    This is not yet supported.
                    This is due to a range of assumptions being made
                    internally that assume a single jaw system.
                    There are some cases where this restriction is
                    too tight. Currently however there is not enough
                    testing data to appropriately implement these
                    cases.
                    If you would like to have your device supported
                    please consider uploading anonymised DICOM files
                    and their TRF counterparts to the following
                    issue
                    <https://github.com/pymedphys/pymedphys/issues/1142>.

                """
            ).format(
                supported_configurations="\n* ".join(
                    [str(item) for item in supported_configurations]
                ),
                rt_beam_limiting_device_types=rt_beam_limiting_device_types,
            )
        )


class DeliveryDicom(DeliveryBase):
    @classmethod
    def from_dicom(cls, rtplan: dicom_path_or_dataset, fraction_group_number=None):
        """Create a ``pymedphys.Delivery`` object from an RT Plan DICOM
        dataset.

        Parameters
        ----------
        rtplan : pydicom.Dataset or pathlib.Path
            An RT Plan DICOM dataset, or the filepath to such a dataset.
        fraction_group_number : 'all' or int, optional
            This parameter is only required when there are more than one
            perscriptions within the provided RT plan file. This
            represents the particular perscription to be converted. The
            number required here must match the corresponding
            FractionGroupNumber within the RT plan file. You may also
            provide 'all' here and all fraction groups will be exported
            as a dictionary of pymedphys.Delivery indexed by the
            FractionGroupNumber.

        Returns
        -------
        delivery : pymedphys.Delivery or dict of pymedphys.Delivery

        """

        if isinstance(rtplan, pydicom.Dataset):
            rtplan_dataset = cast(pydicom.Dataset, rtplan)
        else:
            rtplan_filepath = cast(os.PathLike, rtplan)
            rtplan_dataset = _load_dicom_file(rtplan_filepath)

        if str(fraction_group_number).lower() == "all":
            return cls._load_all_fraction_groups(rtplan_dataset)

        if fraction_group_number is None:
            fraction_groups = rtplan_dataset.FractionGroupSequence
            fraction_group_numbers = [
                fraction_group.FractionGroupNumber for fraction_group in fraction_groups
            ]

            if len(fraction_group_numbers) == 1:
                fraction_group_number = fraction_group_numbers[0]
            else:
                raise ValueError(
                    "There is more than one fraction group in this DICOM plan, please provide"
                    " the `fraction_group_number` parameter to define which one to pull.\n"
                    f"   Fraction numbers to choose from are: {fraction_group_numbers}"
                )

        (
            beam_sequence,
            metersets,
        ) = _pmp_rtplan.get_fraction_group_beam_sequence_and_meterset(
            rtplan_dataset, fraction_group_number
        )

        delivery_data_by_beam_sequence = []
        for beam, meterset in zip(beam_sequence, metersets):
            delivery_data_by_beam_sequence.append(cls._from_dicom_beam(beam, meterset))

        return cls.combine(*delivery_data_by_beam_sequence)

    def to_dicom(self, dicom_template, fraction_group_number=None):
        filtered = self._filter_cps()
        if fraction_group_number is None:
            fraction_group_number = self._fraction_group_number(dicom_template)

        single_fraction_group_template = _pmp_rtplan.convert_to_one_fraction_group(
            dicom_template, fraction_group_number
        )

        template_gantry_angles = _pmp_rtplan.get_gantry_angles_from_dicom(
            single_fraction_group_template
        )

        gantry_tol = utilities.gantry_tol_from_gantry_angles(template_gantry_angles)

        all_masked_delivery_data = (
            filtered._mask_by_gantry(  # pylint: disable = protected-access
                template_gantry_angles, gantry_tol
            )
        )

        fraction_index = _pmp_rtplan.get_fraction_group_index(
            single_fraction_group_template, fraction_group_number
        )

        single_beam_dicoms = []
        for beam_index, masked_delivery_data in enumerate(all_masked_delivery_data):
            single_beam_dicoms.append(
                masked_delivery_data._to_dicom_beam(  # pylint: disable = protected-access
                    single_fraction_group_template, beam_index, fraction_index
                )
            )

        return _pmp_rtplan.merge_beam_sequences(single_beam_dicoms)

    @classmethod
    def _load_all_fraction_groups_from_file(cls, filepath):
        return cls._load_all_fraction_groups(_load_dicom_file(filepath))

    @classmethod
    def _load_all_fraction_groups(cls, dicom_dataset):
        fraction_group_numbers = tuple(
            fraction_group.FractionGroupNumber
            for fraction_group in dicom_dataset.FractionGroupSequence
        )

        all_fraction_groups = {
            fraction_group_number: cls.from_dicom(dicom_dataset, fraction_group_number)
            for fraction_group_number in fraction_group_numbers
        }

        return all_fraction_groups

    @classmethod
    def _from_dicom_file(cls, filepath, fraction_group_number):
        return cls.from_dicom(_load_dicom_file(filepath), fraction_group_number)

    @classmethod
    def _from_dicom_beam(cls, beam, meterset):
        if meterset is None:
            raise ValueError("Meterset should never be None")

        beam_limiting_device_sequence = beam.BeamLimitingDeviceSequence
        _check_for_supported_collimation_device(beam_limiting_device_sequence)

        mlc_sequence = [
            item
            for item in beam_limiting_device_sequence
            if item.RTBeamLimitingDeviceType == "MLCX"
        ]

        if len(mlc_sequence) != 1:
            raise ValueError("Expected there to be only one device labelled as MLCX")

        mlc_limiting_device = mlc_sequence[0]

        leaf_boundaries = mlc_limiting_device.LeafPositionBoundaries
        leaf_widths = np.diff(leaf_boundaries)

        if mlc_limiting_device.NumberOfLeafJawPairs != len(leaf_widths):
            raise ValueError(
                "Expected number of leaf pairs to be the same as "
                "the length of leaf widths"
            )

        num_leaves = len(leaf_widths)

        control_points = beam.ControlPointSequence

        beam_limiting_device_position_sequences = (
            _pmp_rtplan.get_cp_attribute_leaning_on_prior(
                control_points, "BeamLimitingDevicePositionSequence"
            )
        )

        dicom_mlcs = _pmp_rtplan.get_leaf_jaw_positions_for_type(
            beam_limiting_device_position_sequences, "MLCX"
        )

        mlcs = [
            np.array(
                [-np.array(mlc[0:num_leaves][::-1]), np.array(mlc[num_leaves::][::-1])][
                    ::-1
                ]
            ).T
            for mlc in dicom_mlcs
        ]

        dicom_jaw = _pmp_rtplan.get_leaf_jaw_positions_for_type(
            beam_limiting_device_position_sequences, "ASYMY"
        )

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
            _pmp_rtplan.get_cp_attribute_leaning_on_prior(control_points, "GantryAngle")
        )

        collimator_angles = convert_IEC_angle_to_bipolar(
            _pmp_rtplan.get_cp_attribute_leaning_on_prior(
                control_points, "BeamLimitingDeviceAngle"
            )
        )

        return cls(mu, gantry_angles, collimator_angles, mlcs, jaw)

    def _to_dicom_beam(self, dicom_template, beam_index, fraction_index):

        created_dicom = deepcopy(dicom_template)
        data_converted = self._coordinate_convert()

        beam = created_dicom.BeamSequence[beam_index]
        cp_sequence = beam.ControlPointSequence
        initial_cp = cp_sequence[0]
        subsequent_cp = cp_sequence[-1]

        all_control_points = _pmp_rtplan.build_control_points(
            initial_cp, subsequent_cp, data_converted
        )

        beam_meterset = "{0:.6f}".format(data_converted["monitor_units"][-1])
        _pmp_rtplan.replace_fraction_group(
            created_dicom, beam_meterset, beam_index, fraction_index
        )
        _pmp_rtplan.replace_beam_sequence(created_dicom, all_control_points, beam_index)

        _pmp_rtplan.restore_trailing_zeros(created_dicom)

        return created_dicom

    def _matches_fraction_group(
        self, dicom_dataset, fraction_group_number, gantry_tol=3, meterset_tol=0.5
    ):
        filtered = self._filter_cps()
        dicom_metersets = _pmp_rtplan.get_fraction_group_beam_sequence_and_meterset(
            dicom_dataset, fraction_group_number
        )[1]

        rtplan_with_single_fraction_group = _pmp_rtplan.convert_to_one_fraction_group(
            dicom_dataset, fraction_group_number
        )

        gantry_angles = _pmp_rtplan.get_gantry_angles_from_dicom(
            rtplan_with_single_fraction_group
        )

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

    def _fraction_group_number(self, dicom_template, gantry_tol=3, meterset_tol=0.5):
        fraction_groups = dicom_template.FractionGroupSequence

        if len(fraction_groups) == 1:
            return fraction_groups[0].FractionGroupNumber

        fraction_group_numbers = [
            fraction_group.FractionGroupNumber for fraction_group in fraction_groups
        ]

        fraction_group_matches = np.array(
            [
                self._matches_fraction_group(
                    dicom_template,
                    fraction_group_number,
                    gantry_tol=gantry_tol,
                    meterset_tol=meterset_tol,
                )
                for fraction_group_number in fraction_group_numbers
            ]
        )

        if np.sum(fraction_group_matches) < 1:
            raise ValueError(
                "A fraction group was not able to be found with the metersets "
                "and gantry angles defined by the tolerances provided. "
                "Please manually define the fraction group number."
            )

        if np.sum(fraction_group_matches) > 1:
            raise ValueError(
                "More than one fraction group was found that had metersets "
                "and gantry angles within the tolerances provided. "
                "Please manually define the fraction group number."
            )

        fraction_group_number = np.array(fraction_group_numbers)[fraction_group_matches]

        return fraction_group_number

    def _coordinate_convert(self):
        monitor_units = self.monitor_units
        mlc = utilities.mlc_dd2dcm(self.mlc)
        jaw = utilities.jaw_dd2dcm(self.jaw)
        gantry_angle, gantry_movement = utilities.angle_dd2dcm(self.gantry)
        collimator_angle, collimator_movement = utilities.angle_dd2dcm(self.collimator)

        return {
            "monitor_units": monitor_units,
            "mlc": mlc,
            "jaw": jaw,
            "gantry_angle": gantry_angle,
            "gantry_movement": gantry_movement,
            "collimator_angle": collimator_angle,
            "collimator_movement": collimator_movement,
        }
