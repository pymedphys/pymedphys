# Copyright (C) 2019 Simon Biggs, Matt Jennings

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


import numpy as np
import pydicom

from .._level1.create import dicom_dataset_from_dict
from .._level2.anonymise import anonymise_dicom_dataset
from .._level2.dose import (
    extract_dicom_patient_xyz, convert_xyz_to_dicom_coords)

from ...libutils import get_imports

IMPORTS = get_imports(globals())

# pylint: disable=W0201


class DicomBase:
    def __init__(self, dataset):
        self.dataset = dataset

    @classmethod
    def from_file(cls, filepath):
        dataset = pydicom.read_file(filepath, force=True)

        return cls(dataset)

    @classmethod
    def from_dict(cls, dictionary):
        dataset = dicom_dataset_from_dict(dictionary)

        return cls(dataset)

    def __repr__(self):
        return self.dataset.__repr__()

    def save_as(self, filepath):
        self.dataset.save_as(filepath)

    def anonymise(self):
        anonymised = anonymise_dicom_dataset(self.dataset)

        return self.__class__(anonymised)


class DicomDose(DicomBase):

    def __init__(self, dataset):
        super().__init__(dataset)

        self.mask = None

    @property
    def values(self) -> np.ndarray:
        return self.dataset.pixel_array * self.dataset.DoseGridScaling

    @property
    def units(self):
        return self.dataset.DoseUnits

    @units.setter
    def units(self, units_used):
        self.dataset.DoseUnits = units_used

    # TODO: Need to refactor the following to still be a view to the dataset
    # but not needlessly call the entire function.
    @property
    def x(self):
        x_value, _, _ = extract_dicom_patient_xyz(self.dataset)
        return x_value

    @property
    def y(self):
        _, y_value, _ = extract_dicom_patient_xyz(self.dataset)
        return y_value

    @property
    def z(self):
        _, _, z_value = extract_dicom_patient_xyz(self.dataset)
        return z_value

    @property
    def coords(self):
        x, y, z = extract_dicom_patient_xyz(self.dataset)
        return convert_xyz_to_dicom_coords((x, y, z))


class DicomImage(DicomBase):
    pass


class DicomSeries:
    """A series of DicomImages within the same study set.
    """


class DicomStructure(DicomBase):
    pass


class DicomPlan(DicomBase):
    pass


class DicomStudy:
    """A DICOM study can hold one DICOM CT, one DICOM structure, one
    DICOM plan and one DICOM dose. These DICOM files must align via UID
    declaration.

    Not all types are required to create a DicomStudy.
    """


class DicomCollection:
    """A DicomCollection can hold an arbitrary number of DicomStudy objects.
    """
