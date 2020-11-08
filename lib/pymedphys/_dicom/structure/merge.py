# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, shapely

from . import get_roi_contour_sequence_by_name

CONTOUR_GEOMETRIC_TYPE = "CLOSED_PLANAR"


def extract_contours_and_image_sequences(contour_sequence):
    contours_by_z = {}
    image_sequence_by_z = {}

    expected_contour_keys = {
        pydicom.tag.Tag(*tag)
        for tag in [
            (0x3006, 0x0050),
            (0x3006, 0x0046),
            (0x3006, 0x0042),
            (0x3006, 0x0016),
        ]
    }

    for contour in contour_sequence:
        if contour.ContourGeometricType != CONTOUR_GEOMETRIC_TYPE:
            raise ValueError(f"Only {CONTOUR_GEOMETRIC_TYPE} type is supported")

        if set(contour.keys()) != expected_contour_keys:
            raise ValueError("Unexpected contour sequence format")

        contour_data = contour.ContourData

        x = np.array(contour_data[0::3])
        y = np.array(contour_data[1::3])
        z = np.array(contour_data[2::3])

        unique_z = np.unique(z)

        if len(unique_z) != 1:
            raise ValueError("All z values should be equal")

        z = unique_z[0]
        polygon = shapely.geometry.Polygon(zip(x, y))

        try:
            contours_by_z[z].append(polygon)
        except KeyError:
            contours_by_z[z] = [polygon]

        try:
            image_sequence_by_z[z].append(contour.ContourImageSequence)
        except KeyError:
            image_sequence_by_z[z] = [contour.ContourImageSequence]

    return contours_by_z, image_sequence_by_z


def collapse_image_sequence(image_sequence_by_z):
    image_sequence_by_z_collapsed = {}

    expected_image_sequence_keys = {
        pydicom.tag.Tag(*tag) for tag in [(0x0008, 0x1150), (0x0008, 0x1155)]
    }

    for z, image_sequences in image_sequence_by_z.items():
        values = set()

        for image_sequence in image_sequences:
            if len(image_sequence) != 1:
                raise ValueError("Expected only one item per image sequence")

            image_sequence_item = image_sequence[0]

            if set(image_sequence_item.keys()) != expected_image_sequence_keys:
                raise ValueError("Unexpected contour image sequence format")

            values.add(
                (
                    image_sequence_item.ReferencedSOPClassUID,
                    image_sequence_item.ReferencedSOPInstanceUID,
                )
            )

        if len(values) != 1:
            raise ValueError("Each z value should only point to one image slice")

        image_sequence_by_z_collapsed[z] = image_sequences[0]

    return image_sequence_by_z_collapsed


def merge_polygon_contours(contours_by_z):
    all_merged = {}

    for z, contours in contours_by_z.items():
        all_merged[z] = shapely.ops.unary_union(contours)

    return all_merged


def get_coords_from_polygon(polygon):
    return polygon.exterior.coords.xy


def get_coords_from_multipolygon(multipolygon):
    return [get_coords_from_polygon(item) for item in multipolygon]


def get_coords_from_polygon_or_multipolygon(polygon_or_multipolygon):
    try:
        return [get_coords_from_polygon(polygon_or_multipolygon)]
    except AttributeError:
        return get_coords_from_multipolygon(polygon_or_multipolygon)


def format_coords_for_dicom(all_merged):
    dicom_format_coords_by_z = {}

    for z, merged in all_merged.items():
        coords = get_coords_from_polygon_or_multipolygon(merged)
        new_contour_data = []
        for coord in coords:
            stacked_coords = np.hstack(
                list(zip(coord[0], coord[1], z * np.ones_like(coord[1])))
            )
            stacked_coords = np.round(stacked_coords, 1)
            stacked_coords = stacked_coords.tolist()

            new_contour_data.append(stacked_coords)

        dicom_format_coords_by_z[z] = new_contour_data

    return dicom_format_coords_by_z


def create_new_contour_sequence(
    dicom_format_coords_by_z, image_sequence_by_z_collapsed
):
    new_contour_sequence = pydicom.sequence.Sequence()

    for z, contour_items in dicom_format_coords_by_z.items():
        contour_image_sequence = image_sequence_by_z_collapsed[z]
        for contour_data in contour_items:
            new_contour_dataset = pydicom.dataset.Dataset()
            new_contour_dataset.ContourGeometricType = CONTOUR_GEOMETRIC_TYPE
            if len(contour_data) % 3 != 0:
                raise ValueError("The contour points should be divisible by 3")

            new_contour_dataset.NumberOfContourPoints = len(contour_data) // 3
            new_contour_dataset.ContourImageSequence = contour_image_sequence
            new_contour_dataset.ContourData = contour_data

            new_contour_sequence.append(new_contour_dataset)

    return new_contour_sequence


def merge_contours(  # pylint:disable = inconsistent-return-statements
    roi_contour_sequence, inplace=False
):
    try:
        contour_sequence = roi_contour_sequence.ContourSequence
    except AttributeError:
        print(roi_contour_sequence)
        raise

    contours_by_z, image_sequence_by_z = extract_contours_and_image_sequences(
        contour_sequence
    )

    image_sequence_by_z_collapsed = collapse_image_sequence(image_sequence_by_z)
    all_merged = merge_polygon_contours(contours_by_z)

    dicom_format_coords_by_z = format_coords_for_dicom(all_merged)

    new_contour_sequence = create_new_contour_sequence(
        dicom_format_coords_by_z, image_sequence_by_z_collapsed
    )

    if not inplace:
        new_roi_contour_sequence = copy.copy(roi_contour_sequence)
        new_roi_contour_sequence.ContourSequence = new_contour_sequence

        return new_roi_contour_sequence
    else:
        roi_contour_sequence.ContourSequence = new_contour_sequence


def merge_contours_cli(args):
    dicom_dataset = pydicom.read_file(args.input_file, force=True)

    if args.structures is None:
        for roi_contour_sequence in dicom_dataset.ROIContourSequence:
            merge_contours(roi_contour_sequence, inplace=True)
    else:
        for structure in args.structures:
            roi_contour_sequence = get_roi_contour_sequence_by_name(
                structure, dicom_dataset
            )
            merge_contours(roi_contour_sequence, inplace=True)

    pydicom.write_file(args.output_file, dicom_dataset)
