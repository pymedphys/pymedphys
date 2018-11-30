# Copyright (C) 2018 King Paul

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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

"""
@author: king.r.paul@gmail.com
"""

import csv
from string import ascii_letters as LETTERS
from string import digits as DIGITS

import numpy as np


def unshuffle_sinogram(array):
    assert array.shape[1] == 64  # num leaves

    # SPLIT SINOGRAM INTO 51 ANGLE-INDEXED SEGMENTS
    result = [[] for i in range(51)]
    idx = 0
    for row in array:
        result[idx].append(row)
        idx = (idx + 1) % 51

    # EXCLUDE EXTERIOR LEAVES WITH ZERO LEAF-OPEN TIMES
    include = [False for f in range(64)]
    for i, angle in enumerate(result):
        for j, couch_step in enumerate(angle):
            for k, _ in enumerate(couch_step):
                if result[i][j][k] > 0.0:
                    include[k] = True
    gap = max([2 + max(i-32, 31-i) for i, v in enumerate(include) if v])
    result = [[p[31 - gap:32 + gap] for p in result[i]] for i in range(51)]

    return result


def unshuffle_sinogram_csv(file_name):
    """
    Convert a CSV sinogram file into a fluence map collection, by
    unshuffling the sinogram, i.e. separating leaf pattern into
    the 51 tomtherapy discretization angles; display & save result.

    Return a nested list:
        [ [ [leaf-open-fraction] [leaf-open-fraction] ... ]   - couch increment
          [ [leaf-open-fraction] [leaf-open-fraction] ... ]   - couch increment
        ]                                                     - gantry angle
        [   [ [leaf-open-fraction] [leaf-open-fraction] ... ] - couch increment
            [ [leaf-open-fraction] [leaf-open-fraction] ... ] - couch increment
        ]                                                     - gantry angle

    Keyword Args:
        file_name:
            path to csv sinogram file, file formatted as follows
                "Patient name: ANONYMOUS^PATIENT, ID: 00000",,,,,,,,,
                ,0,0,0,0,0,0,0,0,0,0,0,0,,0.39123373,0.366435635 ...
            Demographics on row1, with each following row corresponding
            to a single couch step increment and comprised of 64 cells.
            Each cell in a row corresponding to an mlc leaf, and
            containing its leaf-open fraction.
            This format is produced by ExportTomoSinogram.py, shared by
            Brandon Merz on on the RaySearch customer forum, 1/18/2018.
    """

    with open(file_name, 'r') as csvfile:
        # PATIENT NAME & ID
        pat_name, pat_num = csvfile.readline().split('ID:')
        pat_name = pat_name.replace('Patient name:', '')
        pat_name_last, pat_name_first = pat_name.split('^')

        pat_name_last = ''.join([c for c in pat_name_last if c in LETTERS])
        pat_name_first = ''.join([c for c in pat_name_first if c in LETTERS])
        pat_num = ''.join([c for c in pat_num if c in DIGITS])

        document_id = pat_num + ' - ' + pat_name_last + ', ' + pat_name_first

        # SINOGRAM
        reader = csv.reader(csvfile, delimiter=',')
        array = np.asarray([line[1:] for line in reader]).astype(float)

    result = unshuffle_sinogram(array)

    return document_id, result
