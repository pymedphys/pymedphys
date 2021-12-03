# Copyright (C) 2021 Matthew Jennings
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


import re
from copy import deepcopy
from typing import Sequence

from pymedphys._imports import pydicom

from .create import dicom_dataset_from_dict


def adjust_machine_name(dicom_dataset, new_machine_name):
    """Change the machine name within the DICOM header"""

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
    """Append or adjust relative electron densities of structures"""

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
    """Adjust the structure electron density based on structure name."""
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


def patient_ids_in_datasets_are_equal(
    datasets: Sequence["pydicom.dataset.Dataset"],
) -> bool:
    """True if all DICOM datasets have the same Patient ID

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM datasets whose Patient IDs are to be
        compared.

    Returns
    -------
    bool
        True if Patient IDs match for all datasets, False otherwise.
    """

    return all(ds.PatientID == datasets[0].PatientID for ds in datasets)
