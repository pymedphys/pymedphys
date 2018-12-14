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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


from collections import namedtuple

from scipy import interpolate

from scipy.interpolate import CubicSpline
import matplotlib.pyplot as plt

import numpy as np
from scipy.interpolate import interp1d
import scipy

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def read_prs(file_name):
    """
    Read and return dose profiles and CAX dose from native Profiler data file.

    Arguments:
        file_name -- long file name of profiler file

    Returns:
        The namedtuple Profiler which has the following:
            Profiler.cax = float(dose) at central axis
            Profiler.x = x profile, i.e. [(distance, dose), ...]
            Profiler.y = y profile, i.e. [(distance, dose), ...]
                distance = float(+/- distance from cax
                dose = float(absolute dose at detector)
    """

    Profiler = namedtuple('Profiler', ['cax', 'x', 'y'])

    with open(file_name) as profiler_file:
        for row in profiler_file.readlines():
            contents = row
            if contents[:11] == "Calibration" and "File" not in contents:
                calibs = np.array(contents.split())[1:].astype(float)
            elif contents[:5] == "Data:":
                counts = np.array(contents.split()[5:145]).astype(float)
            elif contents[:15] == "Dose Per Count:":
                dose_per_count = (float(contents.split()[-1]))
        assert (len(calibs)) == (len(counts)) == 140
        assert dose_per_count > 0.0
    dose = counts * dose_per_count * calibs

    y_vals = [-16.4 + 0.4*i for i in range(83)]
    x_vals = [-11.2 + 0.4*i for i in range(57)]

    x_prof = list(zip(y_vals, dose[:57]))
    y_prof = list(zip(x_vals, dose[57:]))

    assert np.allclose(y_prof[41][1], x_prof[28][1])
    cax_dose = y_prof[41][1]

    return Profiler(cax_dose, x_prof, y_prof)


def write_prs(x_prof, y_prof, file_name=None):
    """
    Write dose profiles to a file in the native Profiler data format.

    Arguments:
        x_prof -- x profile, i.e. [(distance, dose), ...]
        y_prof -- y profile, i.e. [(distance, dose), ...]
        file_name -- long file name of profiler file to be written

    Returns:
        None
    """

    # BOILERPLATE PART OF THE FILE
    BIAS_VALUES = ['BIAS1', '', '61200570', '', ''] + ['0.0']*143 + ['0.0\n']
    CAL_VALUES = ['Calibration', '', '', '', ''] + ['1.0']*139 + ['1.0\n']
    LABELS = ['TYPE', 'UPDATE#', 'TIMETIC', 'PULSES', 'ERRORS'] + \
        ['X'+str(i) for i in range(1, 58)] + \
        ['Y'+str(i) for i in range(1, 84)] + \
        ['Z0', 'Z1', 'Z2', 'Z3\n']

    # DOSE VALUES PART OF THE FILE
    COUNTS = []

    x_vals = [-11.2 + 0.4*i for i in range(57)]
    y_vals = [-16.4 + 0.4*i for i in range(83)]

    if [i[0] for i in x_prof] == x_vals and [i[0] for i in y_prof] == y_vals:
        COUNTS = ['Data:', '0', '12151773', '3939', '1'] + \
            [str(int(1000*i[1])) for i in x_prof + y_prof] + \
            ['-129', '463', '1069', '1117\n']
    else:
        x_input = [i[0] for i in x_prof]
        y_input = [i[1] for i in x_prof]
        interpolator = interp1d(x_input, y_input)
        counts_x = [float(i) for i in list(map(interpolator, x_vals))]

        x_input = [i[0] for i in y_prof]
        y_input = [i[1] for i in y_prof]
        interpolator = interp1d(x_input, y_input)
        counts_y = [float(i) for i in list(map(interpolator, y_vals))]

        counts = counts_x + counts_y

        COUNTS = ['Data:', '0', '12151773', '3939', '1'] + \
            [str(int(1000*i)) for i in counts] + \
            ['-129', '463', '1069', '1117\n']

    PRS_FILE_TEMPLATE = ['Version:\t 7\n',
                         'Filename:\tC:\\SNC\\Profiler2\\X04D04.prs\n',
                         'Date:\t 11/10/2018\t Time:\t16:56:28\n',
                         'Description:\t\n',
                         'Institution:\t\n',
                         'Calibration File:\tC:\\SNC\\Profiler2\\Factors\\0000000\\X04.cal\n',
                         '\tProfiler Setup\n', '\n', 'Collector Model:\tProfiler2\n',
                         'Collector Serial:\t4736338 Revision:\tC\n',
                         'Firmware Version:\t1.2.1\n', 'Software Version:\t1.1.0.0\n',
                         'Buildup:\t0\tcm\tWaterEquiv\n',
                         'Nominal Gain\t1\n',
                         'Orientation:\tSagittal\n',
                         'SSD:\t100\tcm\n',
                         'Beam Mode:\tPulsed\n',
                         'Tray Mount:\tNo\n',
                         'Alignment:\tNone\n',
                         'Collection Interval:\t50\n',
                         '\n',
                         '\tMachine Data\n',
                         'Room:\t\n',
                         'Machine Type:\t\n',
                         'Machine Model:\t\n',
                         'Machine Serial Number:\t\n',
                         'Beam Type:\tElectron\tEnergy:\t0 MeV\n',
                         'Collimator:\tLeft: 0 Right: 0 Top: 0 Bottom: 0 cm\n',
                         'Wedge:\tNone\tat\t0\n', 'Rate:\t0\tmu/Min\tDose:\t0\n',
                         'Gantry Angle:\t0 deg\tCollimator Angle:\t0 deg\n',
                         '\n',
                         '\tData Flags\n',
                         'Background Used:\ttrue\n',
                         'Pulse Mode:\ttrue\n',
                         'Analyze Panels:\t1015679\n',
                         '\n',
                         '\tHardware Data\n',
                         'Cal-Serial Number:\t4736338\n',
                         'Cal-Revision:\tC\n',
                         'Temperature:\t-98.96726775\n',
                         'Dose Calibration\n',
                         'Dose Per Count:\t0.001\n',
                         'Dose:\t75.40000153\n',
                         'Absolute Calibration:\tfalse\n',
                         'Energy:\t4 MV\n',
                         'TimeStamp:\t3/16/2008 11:35:0\n',
                         'Comments:\t\n',
                         'Gain Ratios for Amp0:\t\t1\t2\t4\t8\n',
                         'Gain Ratios for Amp1:\t\t1\t2\t4\t8\n',
                         'Gain Ratios for Amp2:\t\t1\t2\t4\t8\n',
                         'Gain Ratios for Amp3:\t\t1\t2\t4\t8\n',
                         '\n', 'Multi Frame:\tfalse\n',
                         '# updates:\t25\n',
                         'Total Pulses:\t3939\n',
                         'Total Time:\t12.151773\n',
                         'Detectors:\t83\t57\t0\t4\n',
                         'Detector Spacing:\t0.4\n',
                         'Concatenation:\tfalse\n',
                         '\t'.join(LABELS),
                         '\t'.join(BIAS_VALUES),
                         '\t'.join(CAL_VALUES),
                         '\t'.join(COUNTS)]

    with open(file_name, 'w') as outfile:
        for line in PRS_FILE_TEMPLATE:
            outfile.write(line)
    return PRS_FILE_TEMPLATE
