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

from collections import namedtuple

import numpy as np
from scipy.interpolate import interp1d


def read_prs(file_name):
    """
    Read native Profiler data file and return dose profiles.

    Parameters
    ----------
    file_name : string
        | file name of Profiler file including path

    Returns
    -------
    Profiler : named tuple
        | Profiler.cax = float dose at central axis
        | Profiler.x = list of (x, dose) tuples
        | Profiler.y = list of (y, dose) tuples
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


def write_prs(x_prof, y_prof,file_name=None,
              version=7,
              meas_date='01/01/1970', meas_time='00:00:01',
              descrip='', instit='', file_cal="NONE", collector='Profiler2',
              coll_sn='0000000', coll_rev='C',
              f_ware_ver='0.0.0', s_ware_v='0.0.0.0',
              depth='1.0', nom_gain='1', orient='Sagittal', ssd='100',
              bm_mode='Pulsed', tray='No', align='None', interval='50',
              room='', mach_type='', mach_mod='',mach_num='',
              bm_modal='Photon', bm_energy='0', jaws=('5','5','5','5'),
              wdg_type='None', wdg_ang='0', rate='0', dose='0',
              gantry='180', collimator='180', bkg_used='true',
              pulse_mode='true', alz_panels='0000000', cal_sn='0000000',
              cal_rev='A', temp='-100', dose_cal = '0.001', d_at_cal='100.0',
              abs_cal='false', energy_cal='0', cal_date='01/01/1970',
              cal_time='00:00:01', cal_cmnts='', m_frame='false',
              updates='0', pulses='0', time='0.0',
              detectors=('83', '57', '0', '4'), spacing='0.4',
              concat='false'):

    """
    Write dose profiles to a file in the native Profiler data format.

    Arguments:
        x_prof -- x profile, i.e. [(distance, dose), ...]
        y_prof -- y profile, i.e. [(distance, dose), ...]

    Keyword Argument [generally needed]:
        file_name -- output long file name, None -> return string only

    Keyword Arguments [not generally needed]:
        ** defaults to reasonable values
        ** many of these values do not affect converted profiles
        ---------
        meas_date -- string, e.g. '11/10/2018'
        meas_time -- string, e.g. '16:56:28'
        descrip   -- string description
        instit    -- string institution
        file_cal  -- long path to calibraiton file, N/A for converted
        collector -- string collector model, i.e. Profiler2
        coll_sn   -- string collector serial number, e.g. '1234567'
        coll_rev  -- string collector revision letter, e.g. 'C'
        f_ware_ver-- string firmware version, e.g. '1.2.1'
        s_ware_v  -- string software version, e.g. '1.1.0.0'
        depth     -- string measurement depth in cm
        nom_gain  -- string nominal gain, e.g. '1',
        orient    -- string orientation, e.g. 'Sagittal',
        ssd       -- string SSD in cm, e.g. '100'
        bm_mode   -- string beam mode, e.g. 'Pulsed'
        tray      -- string e.g. 'No', 'Yes'
        align     -- string, e.g. 'None', 'Light Field', 'Cross Hair'
        interval  -- string collection interval, e.g. 50, must be >0
        room      -- string room description
        mach_type -- string machine type description
        mach_mod  -- string machine model
        mach_num  -- string machine serial number
        bm_modal  -- string beam modality, e.g.'Photon', 'Electron', 'Cobalt'
        bm_energy -- string beam nominal in MV or MeV, e.g. '6'
        jaws      -- tuple of string jaw positions in cm: (l, r, t, b)
        wdg_type  -- string type, e.g. 'None', 'Static', 'Dynamic', 'Virtual'
        wdg_ang   -- string angle, e.g. '0',
        rate      -- string dose rate, e.g. '300'
        dose      -- string total dose, e.g. '100'
        gantry    -- string gantry angle in deg, e.g. '180'
        collimator-- string collimator angle in deg, e.g. '180'
        bkg_used  -- string background used, e.g. 'true'
        pulse_mode-- string pulse mode, e.g.'true'
        alz_panels-- string analyze panels, e.g. ='1015679')
        cal_sn    -- string calibration serial num, e.g. '1234567'
        cal_rev   -- string calibration revision letter, e.g. 'C',
        temp      -- string temparature, internal scale, e.g. '-98.96726775'
        dose_cal  -- string dose per count, e.g. '0.001' for 1000 cts per cGy
        d_at_cal  -- string dose used for absolute calibration, e.g. "75.40153"
        abs_cal   -- string absolute calibration, e.g. 'false', 'true'
        energy_cal-- string energy of calibration, e.g. '4'
        cal_date  -- string, e.g. '11/10/2018'
        cal_time  -- string, e.g. '16:56:28'
        cal_cmnts -- string calibration comments
        m_frame   -- string mult-frame, e.g.'false', 'true
        updates   -- string number of updates, e.g.'25',
        pulses    -- string number of pulses, e.g.'3939'
        time      -- string total measurement time in sec, e.g. '12.5'
        detectors -- tuple of string, Profiler2 -> ('83', '57', '0', '4')
        spacing   -- string detector spacing, e.g.'0.4'
        concat    -- string concatenated measuremets, e.g. 'false'


    Returns:
        The contents of the file as a list of strings.
    """

    # EXTEND PROFILE TAILS, TO ENSURE LONGER THAN DEVICE
    x_prof = [(-1000, 0)] + x_prof + [(1000, 0)]
    y_prof = [(-1000, 0)] + y_prof + [(1000, 0)]

    # X,Y DETECTOR POSITIONS FOR DEVICE
    x_vals = [-11.2 + 0.4*i for i in range(57)]
    y_vals = [-16.4 + 0.4*i for i in range(83)]

    # X,Y COORDINATES CORRECT, DO NOT INTERPOLATE
    if [i[0] for i in x_prof] == x_vals and [i[0] for i in y_prof] == y_vals:
        counts = ['Data:', '0', '0', '0', '0'] + \
            [str(int(1000*i[1])) for i in x_prof + y_prof] + \
            ['0', '0', '0', '0\n']


    else:  # INTERPOLATE X,Y COORDINATES ONTO DETECTOR POSITIONS
        interpolator = interp1d([i[0] for i in x_prof], [i[1] for i in x_prof])
        # counts_x = []
        counts_x = [float(i) for i in list(map(interpolator, x_vals))]

        interpolator = interp1d([i[0] for i in y_prof], [i[1] for i in y_prof])
        # counts_y = []
        counts_y = [float(i) for i in list(map(interpolator, y_vals))]

        # 1000 COUNTS PER CGY
        counts = ['Data:', '0', '0', '0', '0'] + \
            [str(int(1000*i)) for i in counts_x + counts_y] + \
            ['0', '0', '0', '0\n']



    prs_file = ['Version:\t {}\n'.format(7),
                'Filename:\t {} \n'.format('-'),
                'Date:\t {}\t Time:\t{}\n'.format(meas_date, meas_time),
                'Description:\t{}\n'.format(descrip),
                'Institution:\t{}\n'.format(instit),
                'Calibration File:\t{}\n'.format(file_cal),
                '\tProfiler Setup\n', '\n',
                'Collector Model:\t{}\n'.format(collector),
                'Collector Serial:\t{} Revision:\t{}\n'.format(
                    coll_sn, coll_rev),
                'Firmware Version:\t{}\n'.format(f_ware_ver),
                'Software Version:\t{}\n'.format(s_ware_v),
                'Buildup:\t{}\tcm\tWaterEquiv\n'.format(depth),
                'Nominal Gain\t{}\n'.format(nom_gain),
                'Orientation:\t{}\n'.format(orient),
                'SSD:\t{}\tcm\n'.format(ssd),
                'Beam Mode:\t{}\n'.format(bm_mode),
                'Tray Mount:\t{}\n'.format(tray),
                'Alignment:\t{}\n'.format(align),
                'Collection Interval:\t{}\n'.format(interval),
                '\n',
                '\tMachine Data\n',
                'Room:\t{}\n'.format(room),
                'Machine Type:\t{}\n'.format(mach_type),
                'Machine Model:\t{}\n'.format(mach_mod),
                'Machine Serial Number:\t{}\n'.format(mach_num),
                'Beam Type:\t{}\tEnergy:\t{} MeV\n'.format(
                    bm_modal, bm_energy),
                'Collimator:\tLeft: {} Right: {} Top: {} Bottom: {} cm\n'.format(
                   *jaws),
                'Wedge:\t{}\tat\t{}\n'.format(wdg_type, wdg_ang),
                'Rate:\t{}\tmu/Min\tDose:\t{}\n'.format(rate, dose),
                'Gantry Angle:\t{} deg\tCollimator Angle:\t{} deg\n'.format(
                    gantry, collimator),
                '\n',
                '\tData Flags\n',
                'Background Used:\t{}\n'.format(bkg_used),
                'Pulse Mode:\t{}\n'.format(pulse_mode),
                'Analyze Panels:\t{}\n'.format(alz_panels),
                '\n',
                '\tHardware Data\n',
                'Cal-Serial Number:\t{}\n'.format(cal_sn),
                'Cal-Revision:\t{}\n'.format(cal_rev),
                'Temperature:\t{}\n'.format(temp),
                'Dose Calibration\n',
                'Dose Per Count:\t{}\n'.format(dose_cal),
                'Dose:\t{}\n'.format(d_at_cal),
                'Absolute Calibration:\t{}\n'.format(abs_cal),
                'Energy:\t{} MV\n'.format(energy_cal),
                'TimeStamp:\t{} {}\n'.format(cal_date, cal_time),
                'Comments:\t{}\n'.format(cal_cmnts),
                'Gain Ratios for Amp0:\t\t{}\t{}\t{}\t{}\n'.format(1, 2, 4, 8),
                'Gain Ratios for Amp1:\t\t{}\t{}\t{}\t{}\n'.format(1, 2, 4, 8),
                'Gain Ratios for Amp2:\t\t{}\t{}\t{}\t{}\n'.format(1, 2, 4, 8),
                'Gain Ratios for Amp3:\t\t{}\t{}\t{}\t{}\n'.format(1, 2, 4, 8),
                '\n',
                'Multi Frame:\t{}\n'.format(m_frame),
                '# updates:\t{}\n'.format(updates),
                'Total Pulses:\t{}\n'.format(pulses),
                'Total Time:\t{}\n'.format(0.0),
                'Detectors:\t{}\t{}\t{}\t{}\n'.format(*detectors),
                'Detector Spacing:\t{}\n'.format(spacing),
                'Concatenation:\t{}\n'.format(concat),
                '\t'.join(['TYPE',
                           'UPDATE#',
                           'TIMETIC',
                           'PULSES',
                           'ERRORS'] +
                          ['X'+str(i) for i in range(1, 58)] +
                          ['Y'+str(i) for i in range(1, 84)] +
                          ['Z0', 'Z1', 'Z2', 'Z3\n']),
                '\t'.join(['BIAS1', '', '0', '',
                           ''] + ['0.0']*143 + ['0.0\n']),
                '\t'.join(['Calibration', '', '', '', ''] +
                          ['1.0']*139 + ['1.0\n']),
                '\t'.join(counts)]

    with open(file_name, 'w') as outfile:
        for line in prs_file:
            outfile.write(line)
    return prs_file
