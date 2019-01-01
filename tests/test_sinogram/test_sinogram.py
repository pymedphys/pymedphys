# Copyright (C) 2018 Paul King

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


import os

from pymedphys.tomo import read_sin_csv_file
from pymedphys.tomo import read_sin_bin_file
from pymedphys.tomo import crop_sinogram
from pymedphys.tomo import make_histogram
from pymedphys.tomo import find_modulation_factor
from pymedphys.tomo import unshuffle

SIN_CSV_FILE = os.path.join(
    os.path.dirname(__file__), "../data/tomo/sinogram.csv")

SIN_BIN_FILE = os.path.join(
    os.path.dirname(__file__), "../data/tomo/MLC_all_test_old_800P.bin")


def test_read_sin_csv_file():
    pat_id, results = read_sin_csv_file(SIN_CSV_FILE)
    assert pat_id == '00000 - ANONYMOUS, PATIENT'
    num_projections = len(results)
    assert num_projections == 464
    num_leaves = len(results[0])
    assert num_leaves == 64


def test_read_sin_bin_file():
    assert read_sin_bin_file(SIN_BIN_FILE).shape == (400, 64)
# convert this to a nested list


def test_crop_sinogram():
    STRIP = [[0.0]*31 + [1.0]*2 + [0.0]*31,
             [0.0]*31 + [1.0]*2 + [0.0]*31]
    assert crop_sinogram(STRIP) == [[1.0, 1.0], [1.0, 1.0]]


def test_unshuffle():
    unshuffled = unshuffle([[0]*25 + [1.0]*14 + [0]*25]*510)
    assert len(unshuffled) == 51          # number of angles is 51
    assert len(unshuffled[0]) == 10       # number of couch increments
    assert len(unshuffled[0][0]) == 16    # number of visible leaves (is even)
    assert unshuffled[0][0][0] == 0       # first leaf is closed


def test_make_histogram():
    print(make_histogram(None))
    print("test_make_histogram is not implemented")


def test_find_modulation_factor():
    print(find_modulation_factor(None))
    print("test_find_modulation_factor is not implemented")


if __name__ == "__main__":
    # test_read_sin_csv_file()
    # test_read_sin_bin_file()
    test_crop_sinogram()
    # test_unshuffle()
    # test_make_histogram()
    # test_find_modulation_factor()
