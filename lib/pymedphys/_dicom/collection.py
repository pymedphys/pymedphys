# Copyright (C) 2019 Simon Biggs, Matt Jennings

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

from packaging import version
from pymedphys._imports import pydicom

from . import anonymise, coords, create

# pylint: disable=W0201


class DicomBase:
    def __init__(self, dataset, copy=True):
        if copy:
            dataset = deepcopy(dataset)

        create.set_default_transfer_syntax(dataset)

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
        dataset = create.dicom_dataset_from_dict(dictionary)

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
        anonymised = anonymise.anonymise_dataset(self.dataset, copy_dataset=to_copy)

        if not inplace:
            return self.__class__(anonymised)


class DicomDose(DicomBase):
    def __init__(self, dataset, copy=True):
        super().__init__(dataset, copy=copy)

        self.mask = None

    @property
    def values(self):
        return self.dataset.pixel_array * self.dataset.DoseGridScaling

    @property
    def units(self):
        return self.dataset.DoseUnits

    # TODO: Need to refactor the following to still be a view to the dataset
    # but not needlessly call the entire function.
    @property
    def x(self):
        x_value, _, _ = coords.xyz_axes_from_dataset(self.dataset, "DICOM")
        return x_value

    @property
    def y(self):
        _, y_value, _ = coords.xyz_axes_from_dataset(self.dataset, "DICOM")
        return y_value

    @property
    def z(self):
        _, _, z_value = coords.xyz_axes_from_dataset(self.dataset, "DICOM")
        return z_value

    @property
    def coords(self):
        x, y, z = coords.xyz_axes_from_dataset(self.dataset, "DICOM")
        return coords.coords_from_xyz_axes((x, y, z))


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
