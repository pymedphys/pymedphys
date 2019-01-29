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

import dataclasses
import copy

import numpy as np
import xarray as xr

from ...libutils import get_imports
IMPORTS = get_imports(globals())


class XArrayComposition():
    def __init__(self, data, coords=None, dims=None, name=None):
        self._xarray = xr.DataArray(data, coords=coords, dims=dims, name=name)

    @property
    def data(self) -> np.ndarray:
        return self._xarray.data  # type: ignore

    @data.setter
    def data(self, array) -> None:
        array = np.array(array)
        self._xarray.data = array

    def to_xarray(self):
        return self.deepcopy()._xarray

    def to_pandas(self):
        return self.to_xarray().to_pandas()

    def to_dict(self):
        return self.to_xarray().to_dict()

    def deepcopy(self):
        return copy.deepcopy(self)


def xarray_dataclass(cls):
    def __post_init__(self, *args, **kwargs):
        self._create_xarray()

    def _create_xarray(self):
        xarray = xr.Dataset({
            field.name: (field.type, getattr(self, '_' + field.name))
            for field in dataclasses.fields(self)
        })
        object.__setattr__(self, '_xarray', xarray)

    def __iter__(self):
        for field in dataclasses.fields(self):
            yield getattr(self, field.name)

    cls.__post_init__ = __post_init__
    cls._create_xarray = _create_xarray
    cls.__iter__ = __iter__

    cls = dataclasses.dataclass(frozen=True)(cls)

    for field in dataclasses.fields(cls):
        txt = '\n'.join([
            f'@property',
            f'def {field.name}(self):',
            f'    return self._xarray.{field.name}.data',
            '',
            f'@{field.name}.setter',
            f'def {field.name}(self, data):',
            f'    object.__setattr__(self, "_{field.name}", np.array(data))',
            f'    try:',
            f'        self._xarray.{field.name}.data = data',
            f'    except AttributeError:',
            f'        pass',
            '',
            f'cls.{field.name} = {field.name}'
        ])

        exec(txt)

    def to_tuple(self):
        return dataclasses.astuple(self)

    def to_list(self):
        return list(self.to_tuple())

    def to_xarray(self):
        return self.deepcopy()._xarray

    def to_dataframe(self):
        return self.to_xarray().to_dataframe()

    def to_dict(self):
        return self.to_xarray().to_dict()

    def deepcopy(self):
        return copy.deepcopy(self)

    cls.to_tuple = to_tuple
    cls.to_list = to_list
    cls.to_dict = to_dict
    cls.to_xarray = to_xarray
    cls.to_dataframe = to_dataframe
    cls.deepcopy = deepcopy

    return cls
