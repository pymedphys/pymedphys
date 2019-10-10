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

"""@author: king.r.paul@gmail.com
"""


import csv
from os.path import dirname, join
from string import ascii_letters as LETTERS
from string import digits as DIGITS

import numpy as np

from matplotlib import pyplot as plt
from matplotlib.gridspec import GridSpec

from .sinogram import crop, unshuffle


def tomo_sinogram_csv2pdf(file_name="./sinogram.csv", show=True, save=True):
    """
    Convert a CSV sinogram file into a PDF fluence map collection, by
    unshuffling the sinogram, i.e. separating leaf pattern into
    the 51 tomtherapy discretization angles; display & save result.

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
        show: diplay on screen
        save: save to disk
    """

    fig = plt.figure(figsize=(7.5, 11))
    grid_spec = GridSpec(
        nrows=9,
        ncols=6,
        hspace=None,
        wspace=None,
        left=0.05,
        right=0.9,
        bottom=0.02,
        top=0.975,
    )

    with open(file_name, "r") as csvfile:

        # PATIENT NAME & ID
        pat_name, pat_num = csvfile.readline().split("ID:")
        pat_name = pat_name.replace("Patient name:", "")
        pat_name_last, pat_name_first = pat_name.split("^")

        pat_name_last = "".join([c for c in pat_name_last if c in LETTERS])
        pat_name_first = "".join([c for c in pat_name_first if c in LETTERS])
        pat_num = "".join([c for c in pat_num if c in DIGITS])

        document_id = pat_num + " - " + pat_name_last + ", " + pat_name_first

        # SINOGRAM
        reader = csv.reader(csvfile, delimiter=",")
        array = np.asarray([line[1:] for line in reader]).astype(float)

    result = unshuffle(crop(array))

    fig.text(
        0.03, 0.985, document_id, horizontalalignment="left", verticalalignment="center"
    )

    for idx, angle in enumerate(result):
        subplot = fig.add_subplot(grid_spec[idx])
        _ = subplot.imshow(angle, cmap="gray")
        subplot.axes.get_xaxis().set_visible(False)
        subplot.axes.get_yaxis().set_visible(False)
        subplot.set_title("{0:.0f} dg".format(7.06 * idx), fontsize=9)

    if save:
        plt.savefig(join(dirname(file_name), document_id + " Sinogram.pdf"))

    if show:
        plt.show()


if __name__ == "__main__":
    import os

    try:
        test = os.path.join(
            os.getcwd(), "src", "pymedphys", "_labs", "paulking", "sinogram.csv"
        )
        tomo_sinogram_csv2pdf(test, show=True, save=True)
    except IOError:
        print("No sinogram csv file.")
