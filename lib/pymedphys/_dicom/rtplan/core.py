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


from collections import namedtuple

from pymedphys._utilities.transforms import convert_IEC_angle_to_bipolar

Point = namedtuple("Point", ("x", "y", "z"))


class DICOMEntryMissing(ValueError):
    pass


def require_gantries_be_zero(plan):
    gantry_angles = set(get_gantry_angles_from_dicom(plan))
    if gantry_angles != set([0.0]):
        raise ValueError("Only Gantry angles equal to 0.0 are currently supported")


def get_surface_entry_point_with_fallback(plan) -> Point:
    try:
        return get_surface_entry_point(plan)
    except DICOMEntryMissing:
        pass

    require_gantries_be_zero(plan)

    iso_raw = get_single_value_from_control_points(plan, "IsocenterPosition")
    iso = Point(*[float(item) for item in iso_raw])

    source_to_surface = get_single_value_from_control_points(
        plan, "SourceToSurfaceDistance"
    )
    source_to_axis = get_single_value_from_beams(plan, "SourceAxisDistance")

    new_y_value = iso.y + source_to_surface - source_to_axis
    source_entry_point = Point(iso.x, new_y_value, iso.z)

    return source_entry_point


def get_single_value_from_control_points(plan, keyword):
    """Get a named keyword from all control points.

    Raises an error if all values are not the same as each other. Raises an
    error if no value is found.
    """

    values = set()

    for beam in plan.BeamSequence:
        for control_point in beam.ControlPointSequence:
            try:
                value = getattr(control_point, keyword)
            except AttributeError:
                continue

            try:
                values.add(value)
            except TypeError:
                values.add(tuple(value))

    if not values:
        raise DICOMEntryMissing(f"{keyword} was not found within the plan")

    if len(values) > 1:
        raise ValueError(f"More than one disagreeing {keyword} found")

    return values.pop()


def get_single_value_from_beams(plan, keyword):
    """Get a named keyword from all beams.

    Raises an error if all values are not the same as each other. Raises an
    error if no value is found.
    """

    values = set()

    for beam in plan.BeamSequence:
        try:
            value = getattr(beam, keyword)
        except AttributeError:
            continue

        try:
            values.add(value)
        except TypeError:
            values.add(tuple(value))

    if not values:
        raise DICOMEntryMissing(f"{keyword} was not found within the plan")

    if len(values) > 1:
        raise ValueError(f"More than one disagreeing {keyword} found")

    return values.pop()


def get_surface_entry_point(plan) -> Point:
    """
    Parameters
    ----------
    plan : pydicom.Dataset


    Returns
    -------
    surface_entry_point : Point("x", "y", "z")
        Patient surface entry point coordinates (x,y,z) in the
        Patient-Based Coordinate System described in
        Section C.7.6.2.1.1 [1]_ (mm).


    References
    ----------
    .. [1] https://dicom.innolitics.com/ciods/rt-plan/rt-beams/300a00b0/300a0111/300a012e
    """
    # Once we have DicomCollection sorted out, it will likely be worthwhile
    # having this function take a beam sequence parameter, and get the entry
    # point for a given beam sequence
    surface_entry_point_raw = get_single_value_from_control_points(
        plan, "SurfaceEntryPoint"
    )
    surface_entry_point = Point(*[float(item) for item in surface_entry_point_raw])

    return surface_entry_point


def get_metersets_from_dicom(dicom_dataset, fraction_group):
    fraction_group_sequence = dicom_dataset.FractionGroupSequence

    fraction_group_numbers = [
        fraction_group.FractionGroupNumber for fraction_group in fraction_group_sequence
    ]

    fraction_group_index = fraction_group_numbers.index(fraction_group)
    fraction_group = fraction_group_sequence[fraction_group_index]

    beam_metersets = tuple(
        float(referenced_beam.BeamMeterset)
        for referenced_beam in fraction_group.ReferencedBeamSequence
    )

    return beam_metersets


def get_cp_attribute_leaning_on_prior(control_point_sequence, attribute):
    current_result = None
    results = []
    for control_point in control_point_sequence:
        try:
            current_result = getattr(control_point, attribute)

        # If a subsequent control point doesn't record an
        # angle then leave current_angle as what it was in the
        # previous iteration of the loop
        except AttributeError:
            if current_result is None:
                raise

        results.append(current_result)

    return results


def get_gantry_angles_from_dicom(dicom_dataset):

    beam_gantry_angles = []

    for beam_sequence in dicom_dataset.BeamSequence:
        cp_gantry_angles_IEC = get_cp_attribute_leaning_on_prior(
            beam_sequence.ControlPointSequence, "GantryAngle"
        )

        cp_gantry_angles_bipolar = convert_IEC_angle_to_bipolar(cp_gantry_angles_IEC)
        cp_unique_gantry_angles = set(cp_gantry_angles_bipolar)

        beam_gantry_angles.append(cp_unique_gantry_angles)

    for cp_unique_gantry_angles in beam_gantry_angles:
        if len(cp_unique_gantry_angles) != 1:
            raise ValueError(
                "Only a single gantry angle per beam is currently supported"
            )

    result = tuple(list(item)[0] for item in beam_gantry_angles)

    return result


def get_leaf_jaw_positions_for_type(
    beam_limiting_device_position_sequences, rt_beam_limiting_device_type
):
    leaf_jaw_positions = []

    for sequence in beam_limiting_device_position_sequences:
        matching_type = [
            item
            for item in sequence
            if item.RTBeamLimitingDeviceType == rt_beam_limiting_device_type
        ]

        if len(matching_type) != 1:
            raise ValueError(
                "Expected exactly one item per control point for a given collimator"
            )

        leaf_jaw_positions.append(matching_type[0].LeafJawPositions)

    return leaf_jaw_positions


def get_fraction_group_index(dicom_dataset, fraction_group_number):
    fraction_group_numbers = [
        fraction_group.FractionGroupNumber
        for fraction_group in dicom_dataset.FractionGroupSequence
    ]

    return fraction_group_numbers.index(fraction_group_number)


def get_referenced_beam_sequence(dicom_dataset, fraction_group_number):
    fraction_group_index = get_fraction_group_index(
        dicom_dataset, fraction_group_number
    )

    fraction_group = dicom_dataset.FractionGroupSequence[fraction_group_index]
    referenced_beam_sequence = fraction_group.ReferencedBeamSequence

    beam_numbers = [
        referenced_beam.ReferencedBeamNumber
        for referenced_beam in referenced_beam_sequence
    ]

    return beam_numbers, referenced_beam_sequence


def get_beam_indices_of_fraction_group(dicom_dataset, fraction_group_number):
    beam_numbers, _ = get_referenced_beam_sequence(dicom_dataset, fraction_group_number)

    beam_sequence_numbers = [
        beam_sequence.BeamNumber for beam_sequence in dicom_dataset.BeamSequence
    ]

    beam_indexes = [
        beam_sequence_numbers.index(beam_number) for beam_number in beam_numbers
    ]

    return beam_indexes


def get_fraction_group_beam_sequence_and_meterset(dicom_dataset, fraction_group_number):
    beam_numbers, referenced_beam_sequence = get_referenced_beam_sequence(
        dicom_dataset, fraction_group_number
    )

    metersets = [
        referenced_beam.BeamMeterset for referenced_beam in referenced_beam_sequence
    ]

    beam_sequence_number_mapping = {
        beam.BeamNumber: beam for beam in dicom_dataset.BeamSequence
    }

    beam_sequence = [
        beam_sequence_number_mapping[beam_number] for beam_number in beam_numbers
    ]

    return beam_sequence, metersets
