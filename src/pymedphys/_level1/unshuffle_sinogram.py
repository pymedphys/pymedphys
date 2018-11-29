"""
Created on Wed Nov 28 2018
This is free software, under the terms of the GNU General Public License
Version 3 (www.gnu.org/licenses) without any implied warranty of
merchantability or fitness for any particular purpose.
@author: king.r.paul@gmail.com
"""

from matplotlib.gridspec import GridSpec
from matplotlib import pyplot as plt
import numpy as np
import csv
from string import ascii_letters as LETTERS
from string import digits as DIGITS

def unshuffle_sinogram(file_name = '.\\sinogram.csv'):
    """
    Convert a CSV sinogram file into a PDF fluence map collection file, by
    unsshuffling the sinogram, i.e. separating leaf pattern into 
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
    gs = GridSpec(nrows=9, ncols=6, hspace=None, wspace=None,
                  left=0.05, right=0.9, bottom=0.02, top=0.975)

    with open(file_name, 'r') as csvfile:

        # PATIENT NAME & ID
        pat_name, pat_num = csvfile.readline().split('ID:')
        pat_name = pat_name.replace('Patient name:', '')
        pat_name_last, pat_name_first = pat_name.split('^')

        pat_name_last  = ''.join([c for c in pat_name_last  if c in LETTERS])
        pat_name_first = ''.join([c for c in pat_name_first if c in LETTERS])
        pat_num  =  ''.join([c for c in pat_num if c in DIGITS])

        document_ID = pat_num + ' - ' + pat_name_last + ', ' + pat_name_first

        fig.text(0.03, 0.985, document_ID,
                 horizontalalignment='left',verticalalignment='center')

        # SINOGRAM
        reader = csv.reader(csvfile, delimiter=',')
        array = np.asarray([line[1:] for line in reader]).astype(float)
        assert array.shape[1] == 64 # num leaves

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

        # CREATE THE FIGURE
        for idx, angle in enumerate(result):
            ax = fig.add_subplot(gs[idx])
            _ = ax.imshow(angle, cmap='gray')
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)
            ax.set_title('{0:.0f} dg'.format(7.06*idx), fontsize=9)

        plt.savefig(document_ID + ' Sinogram.pdf')
        plt.show()
        return result

if __name__ == '__main__':
    unshuffle_sinogram()