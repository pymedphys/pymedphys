# Copyright (C) 2018 Ben Cooper

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


#************************LaunchFluDO   CELL 01************************************************************************
import os
import numpy as np

import matplotlib
#matplotlib.use('Agg')
from scipy import interpolate as interpl
from scipy import stats as spstats
from pylab import rcParams

import matplotlib.pyplot as plt
from matplotlib import cm, colors
from Dyn_to_Dose import Dyn_to_Dose as d2d
import tkinter# as tk
from tkinter import filedialog
import PinRTPlanDCM as pdcm

rcParams['figure.figsize'] = 17, 12

# dynalog_dir_path = r'/home/mpre/tmp_dynalogs_la4'
# pinnacle_dcm_path = r'/home/mpre/tmp2/RTPLAN9869.1.dcm'
init_pin_path = r'D:\RTPlanFromPin'
init_dynalog_path = r'D:\Temp'

dynalog_dir_path = ''  #
pinnacle_dcm_path = ''  #

if not (os.path.exists(dynalog_dir_path) and os.path.exists(pinnacle_dcm_path)):
    root = tkinter.Tk()  # make a top-level instance and hide since it is ugly and big.
    root.withdraw()
    # root.overrideredirect(True) # make it almost invisible - no decorations, 0 size, top left corner.
    # root.geometry('0x0+0+0')
    # root.deiconify() # show window again and lift it to top so it can get focus,
    root.lift()  # otherwise dialogs will end up behind the terminal.

    root.focus_force()

    dynalog_dir_path = filedialog.askdirectory(parent=root, title='Select Dynalog Directory',
                                               initialdir=init_dynalog_path)
    pinnacle_dcm_path = filedialog.askopenfilename(parent=root, title='Pinnacle Directory',
                                                   initialdir=init_pin_path)
    root.destroy()

print("Dynalog path is: ", dynalog_dir_path)
print("Pinnacle PlanarDose path is: ", pinnacle_dcm_path)
assert len(dynalog_dir_path) >= 1, len(pinnacle_dcm_path) >= 1

# read in dynalog directory
my_dyn2dose = d2d(dynalog_dir_path)

# sort them according to attribute "filename".  This orders them by
# time, oldest to newest by virtue of the file naming convention of
# dynalogs
my_dyn2dose.my_logs.sort(key=lambda x: x.filename)
for ml in my_dyn2dose.my_logs:
    hd, tail = os.path.split(ml.filename)
    print(tail)

# calc and reconstruct fluence from Dynalogs
my_dyn2dose.do_calcs(1.0)


#************************LaunchFluDO   CELL 02**************************************************************************
my_od_maps = pdcm.PinRTPlanDCM(pinnacle_dcm_path)
flu_y = [-19.5, -18.5, -17.5, -16.5, -15.5, -14.5, -13.5, -12.5, -11.5, -10.5, -9.75,
         -9.25, -8.75, -8.25, -7.75, -7.25, -6.75, -6.25, -5.75, -5.25, -4.75, -4.25,
         -3.75, -3.25, -2.75, -2.25, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25,
         1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75, 5.25, 5.75, 6.25, 6.75, 7.25, 7.75,
         8.25, 8.75, 9.25, 9.75, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5,
         19.5]
flu_x = np.linspace(-19.95, 19.95, 400)


def jaw_match(pin, dyn, i, j):
    # tolerance to match jaw positions (mm)
    mytol = 2

    # convert dynalog jaw pos to integral mm and using DICOM co-ords
    d_y2 = int(10 * (dyn.my_logs[i].axis_data.jaws.y2.actual)[0])
    d_x2 = int(10 * (dyn.my_logs[i].axis_data.jaws.x2.actual)[0])
    d_y1 = int(-10 * (dyn.my_logs[i].axis_data.jaws.y1.actual)[0])
    d_x1 = int(-10 * (dyn.my_logs[i].axis_data.jaws.x1.actual)[0])

    difs = [abs(d_y2 - int(pin.y2jaw[j])),
            abs(d_x2 - int(pin.x2jaw[j])),
            abs(d_y1 - int(pin.y1jaw[j])),
            abs(d_x1 - int(pin.x1jaw[j]))]
    for d in difs:
        if d >= mytol:
            print('d is ', d)
            return False
    # fall throguh to here means all difs must be < mytol:
    return True
    # print("d_x1: {0}, p_x: {1}".format(d_x1, int(pin.x1jaw[j])))
    # print("d_x2: {0}, p_x: {1}".format(d_x2, int(pin.x2jaw[j])))
    # print("d_y1: {0}, p_y: {1}".format(d_y1, int(pin.y1jaw[j])))
    # print("d_y2: {0}, p_y: {1}".format(d_y2, int(pin.y2jaw[j])))


for i in range(0, len(my_dyn2dose.gant_angle)):
    print("===\n", "i is: ", i);

    # need to use a dictionary here so we know if we have already
    # come across the same gantry angle (ie dealing with split
    # beams at the same gantry angle)

    j = 0
    while True:
        tol = 1.5  # tolerance for gantry angles
        if abs(my_dyn2dose.gant_angle[i] - my_od_maps.gant_angles[j]) <= tol:
            print('potential match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
            if jaw_match(my_od_maps, my_dyn2dose, i, j):
                print('got a match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                my_dyn2dose.od_map_index[i] = j
                break
            else:
                print('jaws do not agree - split beam perhaps?')
                j += 1
        elif ((my_dyn2dose.gant_angle[i] < 0.8) or (my_dyn2dose.gant_angle[i] > 359.2)):
            if ((my_od_maps.gant_angles[j] < 0.8) or (my_od_maps.gant_angles[j] > 359.2)):
                print('potential match near gant 0! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                if jaw_match(my_od_maps, my_dyn2dose, i, j):
                    print('got a match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                    my_dyn2dose.od_map_index[i] = j
                    break
                else:
                    print('jaws do not agree - split beam perhaps?')
                    j += 1
            else:
                print("need to increment j. j old is {0:d}".format(j))
                j += 1
        elif j > my_od_maps.num_beams:
            print("j incremented out of range - didn't get a gantry angle match")
            break
        else:
            j += 1

# Create the Pinnacle zoom list 'my_pin_zoom_list' which
# zooms in on the Pinnacle map according to jaws (y jaws - 1.0 cm)
# pre-allocate the list

my_pin_zoom_list = [None] * my_dyn2dose.num_logs
for i in range(0, my_dyn2dose.num_logs):
    print(i)
    y2 = (my_dyn2dose.my_logs[i].axis_data.jaws.y2.actual)[0]
    x2 = (my_dyn2dose.my_logs[i].axis_data.jaws.x2.actual)[0]
    y1 = (my_dyn2dose.my_logs[i].axis_data.jaws.y1.actual)[0]
    x1 = (my_dyn2dose.my_logs[i].axis_data.jaws.x1.actual)[0]
    # print("y2 is: ", y2)
    # print("y1 is: ",y1)
    # print("x1 is: ",x1)
    # print("x2 is: ",x2)
    # print ("=====", '\r\n')

    rows = np.linspace(-1.0 * (y1 - 0.05), (y2 - 0.05), ((y2 + y1) * 10))
    cols = np.linspace(-1.0 * (x1 - 0.05), (x2 - 0.05), ((x1 + x2) * 10))

    # print(rows)
    # print (cols)

    indx = my_dyn2dose.od_map_index[i]
    # some code to crop our fludo arrays to the same size as pin_zoom
    dm = my_od_maps.flus[indx]
    my_tmp = interpl.RectBivariateSpline(flu_x, flu_x, dm, kx=1, ky=1, s=0)
    my_pin_zoom_list[i] = my_tmp(rows, cols)

    my_dyn2dose.make_interp_single(i, rows, cols)

# plot some fluences and dose maps TODO: Save 1 A4 page per beam.
my_fig = 0


#************************LaunchFluDO   CELL 03**************************************************************************
print(my_dyn2dose.gant_angle)


#************************LaunchFluDO   CELL 04**************************************************************************

import datetime

right_now = datetime.datetime.now()

# get some demographics from Pinnacle Patient
my_pin_dcm = my_od_maps.ds
tt = str(my_pin_dcm.PatientName).split("^")
plan_dt = str(my_pin_dcm.RTPlanDate)
plan_nm = str(my_pin_dcm.RTPlanName)
ts = tt[0].upper() + ", " + tt[1]

# folder path to store PDFs
pdf_dir = r'D:\FluDo_PDF'
fname = tt[0].upper() + "-" + tt[1] + "_" + (right_now.strftime("%Y%m%d-%H%M%S")) + ".pdf"
pdf_path = os.path.join(pdf_dir, fname)

print(pdf_path)


def add_maps(src, norm, title, fig, ax):
    # add plots to a single figure
    im1 = ax.imshow(src, norm=norm)
    ax.set_title(title)
    my_cax = fig.add_axes([0.92, 0.10, 0.02, 0.80])
    my_ticks = [15.0, 25.0, 50.0, (0.98 * np.max(src))]
    cbar = fig.colorbar(im1, cax=my_cax, ticks=my_ticks, label='arb. units')
    return fig, ax


def show_maps(src, norm, title):
    fig1, ax1 = plt.subplots()
    print(type(fig1))
    im1 = ax1.imshow(src, norm=norm)
    ax1.set_title(title)
    my_cax = fig1.add_axes([0.9, 0.1, 0.03, 0.8])
    my_ticks = [15.0, 25.0, 50.0, (0.98 * np.max(src))]
    cbar = fig1.colorbar(im1, cax=my_cax, ticks=my_ticks)
    plt.show(block=False)


def add_histo(diffs, fig, ax, bins=20):
    ax.hist(diffs.flatten(), bins, color='green', alpha=0.8)
    ax.set_title('Histogram of % error (Pinnacle as reference)')
    ax.set_xlabel('Percent error')
    ax.set_ylabel('Counts')
    return fig, ax


def display_histo(diffs, bins=20):
    # hist, edges = np.histogram(diffs, bins=bins)
    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111)
    ax.hist(diffs.flatten(), bins, color='green', alpha=0.8)
    plt.show(block=False)


# my_pin_dcm = my_od_maps.ds

from matplotlib.backends.backend_pdf import PdfPages

pp = PdfPages(pdf_path)

for i in range(0, my_dyn2dose.num_logs):
    f, axarray = plt.subplots(2, 2)

    my_pin_zoom = 100 * my_pin_zoom_list[i]
    pin_indx = my_dyn2dose.od_map_index[i]
    if len(str(my_pin_dcm.BeamSequence[pin_indx].BeamDescription)) <= 1:
        beam_name = "angle {0}".format(my_dyn2dose.gant_angle[i])
    else:
        beam_name = str(my_pin_dcm.BeamSequence[pin_indx].BeamDescription)

    my_pin_amax = np.unravel_index(my_pin_zoom.argmax(), my_pin_zoom.shape)

    print("pinnacle amax index: ")
    print(my_pin_amax)

    # max_fludo = np.max(my_dyn2dose.interp_fluences[i])
    # my_FluDo = 100*(1/max_fludo)*my_dyn2dose.interp_fluences[i]
    my_FluDo = 100 * my_dyn2dose.interp_fluences[i]
    my_fd_amax = np.unravel_index(my_FluDo.argmax(), my_FluDo.shape)

    print("FluDo amax index: ")
    print(my_fd_amax)

    # create the colors.Normalize object (matplotlib)
    my_norm = colors.Normalize(vmin=np.min(my_pin_zoom),
                               vmax=1.05 * np.max(my_pin_zoom), clip=False)

    # create Pinnacle Dose map
    # show_maps(my_pin_zoom, my_norm, 'Pinn Dose Map')
    f1, ax1 = add_maps(my_pin_zoom, my_norm, 'Planned Beam', f, axarray[0, 1])

    # stuff = input("Can you see 'Pinn Dose Map' figure?")

    # DO the 1st gaussian convolution on fluence
    # blur = ndi.filters.gaussian_filter(my_FluDo, 3.2, order=0, mode='reflect',
    #                                    cval=0.00, truncate=6.0)
    blur = my_FluDo
    my_diff_pct = 100 * abs((blur - my_pin_zoom) / np.max(my_pin_zoom))
    ##my_diff_pct = 100*abs((blur - my_pin_zoom)/ np.max(blur))

    my_mode, my_count = spstats.mode(my_diff_pct, axis=0)
    max_mode_diff = np.max(my_mode)

    print('maximum modal diff: %6.3f' % max_mode_diff)
    f2, ax2 = add_maps((blur), my_norm, 'Delivered Dynalog Beam', f, axarray[1, 1])

    # For now, simply find the modal difference and add it on to the
    # FluDo map
    my_diff_dc = 100 * abs((blur - my_pin_zoom) / np.max(my_pin_zoom))
    ##my_diff_dc = 100*abs((blur - my_pin_zoom)/np.max(blur))

    dat = ((0.01 * my_diff_dc) * my_pin_zoom)
    # display_histo(dat)
    f3, ax3 = add_histo(dat, f, axarray[0, 0], 20)

    f4, ax4 = add_maps(0.01 * my_diff_pct * my_pin_zoom, my_norm, 'Difference Map', f, axarray[1, 0])

    hist, edges = np.histogram(dat, bins=40)
    print('{0}'.format(hist))
    print('{0}'.format(edges[0:15]))

    total = np.sum(hist)
    print("total is {0:d}".format(total))
    targ = 0
    targ2 = 0
    delta = 1.01
    delta2 = 3.01
    for edge in edges:
        if edge < delta:
            targ += 1
        if edge < delta2:
            targ2 += 1

    my_fails = np.sum(hist[targ:-1])
    my_pct_pass = 1 - (my_fails / total)

    my_fails2 = np.sum(hist[targ2: -1])
    my_pct_pass2 = 1 - (my_fails2 / total)

    ax4 = axarray[1, 0]
    plt.setp(ax4.get_xticklabels(), visible=False)
    plt.setp(ax4.get_yticklabels(), visible=False)
    ax4.yaxis.set_ticks([])
    ax4.xaxis.set_ticks([])

    ax3.text(0.28, 0.90, ("percentage of pixels < {0:d} % error is {1:.1f}".format(int(delta), 100 * my_pct_pass)),
             horizontalalignment='left', transform=ax3.transAxes, fontsize=14)
    ax3.text(0.28, 0.83, ("percentage of pixels < {0:d} % error is {1:.1f}".format(int(delta2), 100 * my_pct_pass2)),
             horizontalalignment='left', transform=ax3.transAxes, fontsize=14)
    ax3.text(0.28, 0.76, ("Beam angle is: {0:.1f}".format(my_dyn2dose.gant_angle[i])),
             horizontalalignment='left', transform=ax3.transAxes, fontsize=14)

    # tt = str(my_pin_dcm.PatientName).split("^")
    # plan_dt = str(my_pin_dcm.RTPlanDate)
    # plan_nm = str(my_pin_dcm.RTPlanName)
    # ts = tt[0].upper()+", "+ tt[1]
    print(ts)
    f.suptitle('IMRT QA report for patient: {0:s}\nbeam label: {1:s} | Plan Date: {2:s} | Plan name: {3:s}'
               .format(ts, beam_name, plan_dt, plan_nm), fontsize=24)
    plt.show()
    plt.savefig(pp, format='pdf')
    print("targ is: ", targ)
    print("hist[targ] is: ", hist[targ])
    print("pct pass is {0:f}".format(my_pct_pass))

    print(">>>   >>>   >>>", '\r\n', '\r\n')

#
# end for loop
#
pp.close()


