# Copyright (C) 2019 Simon Biggs

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

import pydicom

from .._level1.dcmcreate import dcm_from_dict
from .._level2.dcmanonymise import anonymise_dicom

from ...libutils import get_imports

IMPORTS = get_imports(globals())


class Dicom():
    def __init__(self, dcm):
        self.dcm = dcm

    @classmethod
    def from_file(cls, filepath):
        dcm = pydicom.read_file(filepath, force=True)

        return cls(dcm)

    @classmethod
    def from_dict(cls, dictionary):
        dcm = dcm_from_dict(dictionary)

        return cls(dcm)

    def __repr__(self):
        return self._dcm.__repr__()

    @property
    def dcm(self) -> pydicom.Dataset:
        return deepcopy(self._dcm)

    @dcm.setter
    def dcm(self, dcm: pydicom.Dataset):
        self._dcm = deepcopy(dcm)

    def save_as(self, filepath):
        self._dcm.save_as(filepath)

    def anonymise(self):
        anonymised = anonymise_dicom(self.dcm)

        return self.__class__(anonymised)
