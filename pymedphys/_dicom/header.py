# Copyright (C) 2019 Cancer Care Associates

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


import re
from copy import deepcopy

import pydicom

from .create import dicom_dataset_from_dict


def adjust_machine_name(dicom_dataset, new_machine_name):
    """Change the machine name within the DICOM header
    """

    new_dicom_dataset = deepcopy(dicom_dataset)

    for beam in new_dicom_dataset.BeamSequence:
        beam.TreatmentMachineName = new_machine_name

    return new_dicom_dataset


def adjust_machine_name_cli(args):
    dicom_dataset = pydicom.read_file(args.input_file, force=True)
    new_dicom_dataset = adjust_machine_name(dicom_dataset, args.new_machine_name)

    pydicom.write_file(args.output_file, new_dicom_dataset)


def delete_sequence_item_with_matching_key(sequence, key, value):
    new_sequence = deepcopy(sequence)

    for i, item in reversed(list(enumerate(sequence))):
        try:
            if value == getattr(item, key):
                new_sequence.pop(i)
        except AttributeError:
            pass

    return new_sequence


def adjust_rel_elec_density(
    dicom_dataset, adjustment_map, ignore_missing_structure=False
):
    """Append or adjust relative electron densities of structures
    """

    new_dicom_dataset = deepcopy(dicom_dataset)

    ROI_name_to_number_map = {
        structure_set.ROIName: structure_set.ROINumber
        for structure_set in new_dicom_dataset.StructureSetROISequence
    }

    ROI_number_to_observation_map = {
        observation.ReferencedROINumber: observation
        for observation in new_dicom_dataset.RTROIObservationsSequence
    }

    for structure_name, new_red in adjustment_map.items():
        try:
            ROI_number = ROI_name_to_number_map[structure_name]
        except KeyError:
            if ignore_missing_structure:
                continue

            raise

        observation = ROI_number_to_observation_map[ROI_number]

        try:
            physical_properties = observation.ROIPhysicalPropertiesSequence
        except AttributeError:
            physical_properties = []

        physical_properties = delete_sequence_item_with_matching_key(
            physical_properties, "ROIPhysicalProperty", "REL_ELEC_DENSITY"
        )

        physical_properties.append(
            dicom_dataset_from_dict(
                {
                    "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                    "ROIPhysicalPropertyValue": new_red,
                }
            )
        )

        observation.ROIPhysicalPropertiesSequence = physical_properties

    return new_dicom_dataset


def adjust_RED_cli(args):
    adjustment_map = dict(zip(args.adjustment_map[::2], args.adjustment_map[1::2]))

    dicom_dataset = pydicom.read_file(args.input_file, force=True)
    new_dicom_dataset = adjust_rel_elec_density(
        dicom_dataset,
        adjustment_map,
        ignore_missing_structure=args.ignore_missing_structure,
    )

    pydicom.write_file(args.output_file, new_dicom_dataset)


def RED_adjustment_map_from_structure_names(structure_names):
    structure_name_containing_RED_regex = r"^.*RED\s*[=:]\s*(\d+\.?\d*)\s*$"
    pattern = re.compile(structure_name_containing_RED_regex, flags=re.IGNORECASE)

    adjustment_map = {
        structure: float(pattern.match(structure).group(1))
        for structure in structure_names
        if pattern.match(structure)
    }

    return adjustment_map


def adjust_RED_by_structure_name(dicom_dataset):
    """Adjust the structure electron density based on structure name.
    """
    structure_names = [
        structure_set.ROIName for structure_set in dicom_dataset.StructureSetROISequence
    ]

    adjustment_map = RED_adjustment_map_from_structure_names(structure_names)

    adjusted_dicom_dataset = adjust_rel_elec_density(dicom_dataset, adjustment_map)

    return adjusted_dicom_dataset


def adjust_RED_by_structure_name_cli(args):
    dicom_dataset = pydicom.read_file(args.input_file, force=True)
    new_dicom_dataset = adjust_RED_by_structure_name(dicom_dataset)

    pydicom.write_file(args.output_file, new_dicom_dataset)
