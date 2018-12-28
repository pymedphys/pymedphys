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

from pymedphys.tomo import read_bin_file
from pymedphys.tomo import crop
from pymedphys.tomo import make_histogram
from pymedphys.tomo import find_modulation_factor
from pymedphys.tomo import unshuffle
from pymedphys.tomo import unshuffle_sinogram_csv

SINOGRAM_FILE = os.path.join(
    os.path.dirname(__file__), "../data/tomo/sinogram.csv")


def test_read_bin_file():
    print(read_bin_file(None))
    print("read_bin_file is not implemented")


def test_crop():
    print(crop(None))
    print("test_crop is not implemented")


def test_make_histogram():
    print(make_histogram(None))
    print("test_make_histogram is not implemented")


def test_find_modulation_factor():
    print(find_modulation_factor(None))
    print("test_find_modulation_factor is not implemented")


def test_unshuffle():
    unshuffled = unshuffle([[0]*25 + [1.0]*14 + [0]*25]*510)
    assert len(unshuffled) == 51          # number of angles is 51
    assert len(unshuffled[0]) == 10       # number of couch increments
    assert len(unshuffled[0][0]) == 16    # number of visible leaves (is even)
    assert unshuffled[0][0][0] == 0       # first leaf is closed


def test_unshuffle_sinogram_csv():
    document_id, results = unshuffle_sinogram_csv(SINOGRAM_FILE)
    assert document_id == '00000 - ANONYMOUS, PATIENT'
    assert len(results) == 51


if __name__ == "__main__":
    test_read_bin_file()
    test_crop()
    test_make_histogram()
    test_find_modulation_factor()
    test_unshuffle()
    test_unshuffle_sinogram_csv()
