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

from matplotlib.gridspec import GridSpec
from matplotlib import pyplot as plt


from pymedphys.tomo import unshuffle_sinogram_csv


def main(file_name='./sinogram.csv'):
    """
    Convert a CSV sinogram file into a PDF fluence map collection file, by
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

    fig = plt.figure(figsize=(7.5, 11))
    grid_spec = GridSpec(nrows=9, ncols=6, hspace=None, wspace=None,
                         left=0.05, right=0.9, bottom=0.02, top=0.975)

    document_id, result = unshuffle_sinogram_csv(file_name)

    fig.text(0.03, 0.985, document_id,
             horizontalalignment='left', verticalalignment='center')

    for idx, angle in enumerate(result):
        ax = fig.add_subplot(grid_spec[idx])
        _ = ax.imshow(angle, cmap='gray')
        ax.axes.get_xaxis().set_visible(False)
        ax.axes.get_yaxis().set_visible(False)
        ax.set_title('{0:.0f} dg'.format(7.06*idx), fontsize=9)

    plt.savefig(document_id + ' Sinogram.pdf')
    plt.show()


if __name__ == '__main__':
    main()
