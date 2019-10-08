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


from copy import deepcopy

import numpy as np

import pydicom

from packaging import version

from .anonymise import anonymise_dataset
from .coords import coords_from_xyz_axes, xyz_axes_from_dataset
from .create import dicom_dataset_from_dict

# pylint: disable=W0201


class DicomBase:
    def __init__(self, dataset, copy=True):
        if copy:
            dataset = deepcopy(dataset)

        if dataset.is_little_endian is None:
            dataset.is_little_endian = True

        if dataset.is_implicit_VR is None:
            dataset.is_implicit_VR = True

        self.dataset = dataset

    @classmethod
    def from_file(cls, fp):
        """Instantiate a DicomBase instance from a filepath or file-like
        object.
        """
        dataset = pydicom.dcmread(fp, force=True)

        return cls(dataset)

    def to_file(self, fp):
        """Write the DicomBase instance's dataset to a file denoted by
        a filepath or file-like object.
        """
        self.dataset.save_as(fp)

    @classmethod
    def from_dict(cls, dictionary):
        """Instantiate a DicomBase instance from a dictionary of
        DICOM keyword/value pairs.
        """
        dataset = dicom_dataset_from_dict(dictionary)

        return cls(dataset)

    def _pydicom_eq(self, other):
        return self.dataset == other.dataset

    def __repr__(self):
        return self.dataset.__repr__()

    def __eq__(self, other):
        if version.parse(pydicom.__version__) <= version.parse("1.2.1"):
            self_elems = sorted(list(self.dataset.iterall()), key=lambda x: x.tag)
            other_elems = sorted(list(other.dataset.iterall()), key=lambda x: x.tag)
            return self_elems == other_elems

        # TODO: Change for pydicom>=1.2.2?
        self_elems = sorted(list(self.dataset.iterall()), key=lambda x: x.tag)
        other_elems = sorted(list(other.dataset.iterall()), key=lambda x: x.tag)
        return self_elems == other_elems

    def __ne__(self, other):
        return not self == other

    def anonymise(  # pylint: disable = inconsistent-return-statements
        self, inplace=False
    ):
        to_copy = not inplace
        anonymised = anonymise_dataset(self.dataset, copy_dataset=to_copy)

        if not inplace:
            return self.__class__(anonymised)


class DicomDose(DicomBase):
    def __init__(self, dataset, copy=True):
        super().__init__(dataset, copy=copy)

        self.mask = None

    @property
    def values(self) -> np.ndarray:
        return self.dataset.pixel_array * self.dataset.DoseGridScaling

    @property
    def units(self):
        return self.dataset.DoseUnits

    # TODO: Need to refactor the following to still be a view to the dataset
    # but not needlessly call the entire function.
    @property
    def x(self):
        x_value, _, _ = xyz_axes_from_dataset(self.dataset, "DICOM")
        return x_value

    @property
    def y(self):
        _, y_value, _ = xyz_axes_from_dataset(self.dataset, "DICOM")
        return y_value

    @property
    def z(self):
        _, _, z_value = xyz_axes_from_dataset(self.dataset, "DICOM")
        return z_value

    @property
    def coords(self):
        x, y, z = xyz_axes_from_dataset(self.dataset, "DICOM")
        return coords_from_xyz_axes((x, y, z))


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
