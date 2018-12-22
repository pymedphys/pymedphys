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

from pymedphys.tomo import unshuffle_sinogram
from pymedphys.tomo import unshuffle_sinogram_csv

SINOGRAM_FILE = os.path.join(
    os.path.dirname(__file__), "../data/tomo/sinogram.csv")


def test_unshuffle_sinogram():
    """ Compare unshuffle_sinogram results vs expected values """
    unshuffled = unshuffle_sinogram([[0]*25 + [1.0]*14 + [0]*25]*510)
    assert len(unshuffled) == 51          # number of angles is 51
    assert len(unshuffled[0]) == 10       # number of couch increments
    assert len(unshuffled[0][0]) == 16    # number of visible leaves (is even)
    assert unshuffled[0][0][0] == 0       # first leaf is closed


def test_unshuffle_sinogram_csv():
    """ Compare unshuffle_sinogram_csv results vs expected """
    document_id, results = unshuffle_sinogram_csv(SINOGRAM_FILE)
    assert document_id == '00000 - ANONYMOUS, PATIENT'
    assert len(results) == 51


if __name__ == "__main__":
    test_unshuffle_sinogram()
    test_unshuffle_sinogram_csv()
