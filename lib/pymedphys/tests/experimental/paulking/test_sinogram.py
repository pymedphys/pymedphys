# Copyright (C) 2018 Paul King

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import numpy as np

from pymedphys._data import download

from pymedphys._experimental.paulking.sinogram import (
    crop,
    find_modulation_factor,
    make_histogram,
    read_bin_file,
    read_csv_file,
    unshuffle,
)


def get_sinogram_csv_path():
    return download.get_file_within_data_zip("paulking_test_data.zip", "sinogram.csv")


def test_read_csv_file():
    pat_id, results = read_csv_file(get_sinogram_csv_path())
    assert pat_id == "00000 - ANONYMOUS, PATIENT"
    num_projections = len(results)
    assert num_projections == 464
    num_leaves = len(results[0])
    assert num_leaves == 64


def test_read_bin_file():
    assert read_bin_file(
        download.get_file_within_data_zip(
            "paulking_test_data.zip", "MLC_all_test_old_800P.bin"
        )
    ).shape == (400, 64)


# convert this to a nested list


def test_crop():
    STRIP = [[0.0] * 31 + [1.0] * 2 + [0.0] * 31, [0.0] * 31 + [1.0] * 2 + [0.0] * 31]
    assert crop(STRIP) == [[1.0, 1.0], [1.0, 1.0]]


def test_unshuffle():
    unshuffled = unshuffle([[0] * 25 + [1.0] * 14 + [0] * 25] * 510)
    assert len(unshuffled) == 51  # number of angles
    assert len(unshuffled[0]) == 10  # number of projections
    assert unshuffled[0][0][0] == 0  # first leaf is closed


def test_make_histogram():
    sinogram = read_csv_file(get_sinogram_csv_path())[-1]
    assert np.allclose(make_histogram(sinogram)[0][0], [0.0, 0.1])
    assert make_histogram(sinogram)[0][1] == 25894
    # [(array([0. , 0.1]), 25894),
    #  (array([0.1, 0.2]), 0),
    #  (array([0.2, 0.3]), 11),
    #  (array([0.3, 0.4]), 3523), ...]


def test_find_modulation_factor():
    sinogram = read_csv_file(get_sinogram_csv_path())[-1]
    assert np.isclose(find_modulation_factor(sinogram), 2.762391)
