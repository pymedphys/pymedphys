# Copyright (C) 2019-2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys import Delivery

# pylint: disable = protected-access


def test_object_consistency():
    empty = Delivery._empty()
    filtered = empty._filter_cps()

    assert isinstance(filtered.monitor_units, tuple)

    filtered._metersets(0, 0)


def test_base_object():
    empty = Delivery._empty()

    assert empty.monitor_units == tuple()

    collection = {field: getattr(empty, field) for field in empty._fields}

    dummy = Delivery(**collection)
