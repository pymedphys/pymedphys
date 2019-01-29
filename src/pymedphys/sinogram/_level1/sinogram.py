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
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""
@author: king.r.paul@gmail.com
"""

from string import digits as DIGITS
from string import ascii_letters as LETTERS
import csv

import numpy as np

from ...libutils import get_imports
IMPORTS = get_imports(globals())


def read_csv_file(file_name):
    # Temporarily disabling docstring due to "Unexpected indentation"
    # error within Sphinx build

    # """
    # Return patient ID and sinogram array produced by reading a RayStation sinogram
    # CSV file with the provided file name.

    # Files are produced by ExportTomoSinogram.py, Brandon Merz,
    # RaySearch customer forum, 1/18/2018.

    #     Format:
    #         First row contains demographics. Subsequent rows correspond to couch positions.
    #         Leaf-open time range from zero to one.
    #             "Patient name: ANONYMOUS^PATIENT, ID: 00000",,,,,,,,,
    #             ,0,0,0,0,0,0,0,0,0,0,0,0,0.39123373,0.366435635 ...
    # """

    with open(file_name, 'r') as csvfile:

        pat_name, pat_num = csvfile.readline().split('ID:')
        pat_name = pat_name.replace('Patient name:', '')

        pat_name_last, pat_name_first = pat_name.split('^')
        pat_name_last = ''.join([c for c in pat_name_last if c in LETTERS])
        pat_name_first = ''.join([c for c in pat_name_first if c in LETTERS])
        pat_num = ''.join([c for c in pat_num if c in DIGITS])

        document_id = pat_num + ' - ' + pat_name_last + ', ' + pat_name_first
        reader = csv.reader(csvfile, delimiter=',')
        array = np.asarray([line[1:] for line in reader]).astype(float)

    return document_id, array


def read_bin_file(file_name):
    """
    Return sinogram np.array produced by reading an Accuray sinogram
    BIN file with the provided file name. BIN files are sinograms
    stored in binary format used in Tomotherapy calibration plans.

    """
    leaf_open_times = np.fromfile(file_name, dtype=float,
                                  count=-1, sep='')
    num_leaves = 64
    num_projections = int(len(leaf_open_times)/num_leaves)
    sinogram = np.reshape(leaf_open_times, (num_projections, num_leaves))

    return sinogram


def crop(sinogram):
    """
    Return a symmetrically cropped sinogram, such that always-closed
    leaves are excluded and the sinogram center is maintained.

    """
    include = [False for f in range(64)]
    for i, projection in enumerate(sinogram):
        for j, leaf in enumerate(projection):
            if sinogram[i][j] > 0.0:
                include[j] = True
    include = include or include[::-1]
    idx = [i for i, yes in enumerate(include) if yes]
    sinogram = [[projection[i] for i in idx] for projection in sinogram]
    return sinogram


def unshuffle(sinogram):
    """
    Return a list of 51 sinograms, by unshuffling the provided
    sinogram; so that all projections in the result correspond
    to the same gantry rotation angle.

    """
    unshufd = [[] for i in range(51)]
    idx = 0
    for prj in sinogram:
        unshufd[idx].append(prj)
        idx = (idx + 1) % 51
    return unshufd


def make_histogram(sinogram, num_bins=10):
    """
    Return a histogram of leaf-open-times for the provided sinogram
    comprised of the specified number of bins, in the form of a list
    of tuples: [(bin, count)...] where bin is a 2-element array setting
    the bounds and count in the number leaf-open-times in the bin.

    """

    lfts = sinogram.flatten()

    bin_inc = (max(lfts) - min(lfts)) / num_bins
    bin_min = min(lfts)
    bin_max = max(lfts)

    bins_strt = np.arange(bin_min, bin_max,  bin_inc)
    bins_stop = np.arange(bin_inc, bin_max+bin_inc, bin_inc)
    bins = np.dstack((bins_strt, bins_stop))[0]

    counts = [0 for b in bins]

    for lft in lfts:
        for idx, bin in enumerate(bins):
            if lft >= bin[0] and lft < bin[1]:
                counts[idx] = counts[idx] + 1

    histogram = list(zip(bins, counts))

    return histogram


def find_modulation_factor(sinogram):
    """
    Return as float the ratio of the maximum leaf open time (assumed
    fully open) to the mean leaf open time, as determined over all
    non-zero leaf open times, where zero is interpreted as blocked
    versus modulated.

    """
    lfts = [lft for lft in sinogram.flatten() if lft > 0.0]
    modulation_factor = max(lfts) / np.mean(lfts)

    return modulation_factor
