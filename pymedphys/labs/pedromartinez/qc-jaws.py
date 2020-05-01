#############################START LICENSE##########################################
# Copyright (C) 2019 Pedro Martinez
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#############################END LICENSE##########################################


###########################################################################################
#
#   Script name: qc-lightrad
#
#   Description: This script performs automated EPID QC of the QC-3 phantom developed in Manitoba.
#   There are other tools out there that do this but generally the ROI are fixed whereas this script
#   aims to dynamically identify them using machine vision and the bibs in the phantom.
#
#   Example usage: python qc-jaws "/folder/"
#
#   Tool for calculating jaws junction shifts for linear accelerators. The script opens every DICOM
#   file in a given folder and creates a combined profile resulting from the superposition of the
#   two or more fields. It then detects the peak/through formed by the gap/overlap of the fields.
#   A window is then selected around this point and a Savitzky-Golay smoothing filter is then applied
#   to the combined profile. This new curve is then used iteratively to minimize the profile created
#   every time one of the profiles slide to close the gap or decrease the overlap. The profile will
#   achieve it greatest level of homogeneity when the dosimetric penumbra of both fields are
#   matched in space. The final result is the optimal calculation of the gap/overlap between the
#   two profiles. The software generates a pdf file with a summary of all the results.
#
#   The folder should contain:
#   2 X-jaws images
#   2 or 3 Y-jaws images
#   4 Field rotation images
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-04-09
#
###########################################################################################

import argparse
import os

from pymedphys._imports import numpy as np
from pymedphys._imports import plt, pydicom
from tqdm import tqdm

from scipy import signal

from matplotlib.backends.backend_pdf import PdfPages

from pymedphys.labs.pedromartinez.utils import minimize_field_rot as minFR
from pymedphys.labs.pedromartinez.utils import minimize_junction_X as minX
from pymedphys.labs.pedromartinez.utils import minimize_junction_Y as minY
from pymedphys.labs.pedromartinez.utils import peak_find as pf
from pymedphys.labs.pedromartinez.utils import peak_find_fieldrot as pffr
from pymedphys.labs.pedromartinez.utils import utils as u


# axial visualization and scrolling
def multi_slice_viewer(volume, dx, dy):
    # remove_keymap_conflicts({'j', 'k'})
    fig, ax = plt.subplots()
    ax.volume = volume
    ax.index = volume.shape[2] // 2
    print(ax.index)
    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))
    ax.imshow(volume[:, :, ax.index], extent=extent)
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")
    ax.set_title("item=" + str(ax.index))
    fig.suptitle("Axial view", fontsize=16)
    fig.canvas.mpl_connect("key_press_event", process_key_axial)


def process_key_axial(event):
    fig = event.canvas.figure
    ax = fig.axes[0]
    if event.key == "j":
        previous_slice_axial(ax)
    elif event.key == "k":
        next_slice_axial(ax)
    ax.set_title("item=" + str(ax.index))
    fig.canvas.draw()


def previous_slice_axial(ax):
    volume = ax.volume
    ax.index = (ax.index - 1) % volume.shape[2]  # wrap around using %
    # print(ax.index, volume.shape[2])
    ax.images[0].set_array(volume[:, :, ax.index])


def next_slice_axial(ax):
    volume = ax.volume
    ax.index = (ax.index + 1) % volume.shape[2]
    # print(ax.index, volume.shape[2])
    ax.images[0].set_array(volume[:, :, ax.index])


# this subroutine will merge the two jaws into a single image and display a graph of the overlap
def merge_view_vert(volume, dx, dy):
    junctions = []

    # creating merged volume
    merge_vol = np.zeros((volume.shape[0], volume.shape[1]))

    # creating vector for processing along cols (one row)
    amplitude = np.zeros(
        (volume.shape[1], volume.shape[2])
    )  # 1 if it is vertical 0 if the bars are horizontal

    x = np.linspace(
        0, 0 + (volume.shape[1] * dx), volume.shape[1], endpoint=False
    )  # definition of the distance axis
    # x = np.arange(0,)#definition of the distance axis

    # merging the two images together
    ampl_resamp = np.zeros(((volume.shape[1]) * 10, volume.shape[2]))
    # amp_peak = np.zeros((volume.shape[1]) * 10)

    for item in tqdm(range(0, volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, item]
        amplitude[:, item] = volume[int(volume.shape[0] / 2), :, item]
        ampl_resamp[:, item] = signal.resample(
            amplitude[:, item], int(len(amplitude)) * 10
        )  # resampling the amplitude vector
        # amp_peak = amp_peak + ampl_resamp[:, item] / volume.shape[2]

    fig, ax = plt.subplots(nrows=2, squeeze=True, figsize=(6, 8))

    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))

    ax[0].imshow(merge_vol, extent=extent)
    # ax[0].set_aspect('equal', 'box')
    ax[0].set_xlabel("x distance [mm]")
    ax[0].set_ylabel("y distance [mm]")

    ax[1].plot(x, amplitude)
    ax[1].set_xlabel("x distance [mm]")
    ax[1].set_ylabel("amplitude")
    ax[1].legend()
    fig.suptitle("Merged volume", fontsize=16)

    # peaks, peak_type, peak_figs = peak_find(ampl_resamp, dx)
    peaks, peak_type, peak_figs = pf.peak_find(ampl_resamp, dx)
    junction_figs = minX.minimize_junction_X(ampl_resamp, peaks, peak_type, dx / 10)
    junctions.append(junction_figs)

    return fig, peak_figs, junctions


# this subroutine will merge the 4 jaws and analyze them
# each jaw is 6cm in length (60mm)
def merge_view_horz(volume, dx, dy):
    junctions = []

    # creating merged volume
    merge_vol = np.zeros((volume.shape[0], volume.shape[1]))

    # creating vector for processing along cols (one row)
    amplitude = np.zeros(
        (volume.shape[0], volume.shape[2])
    )  # 1 if it is vertical 0 if the bars are horizontal

    y = np.linspace(
        0, 0 + (volume.shape[0] * dy), volume.shape[0], endpoint=False
    )  # definition of the distance axis
    # x = np.arange(0,) #definition of the distance axis

    # merging the two images together
    ampl_resamp = np.zeros(((volume.shape[0]) * 10, volume.shape[2]))
    # amp_peak = np.zeros((volume.shape[0]) * 10)

    for item in tqdm(range(0, volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, item]
        amplitude[:, item] = volume[:, int(volume.shape[1] / 2), item]
        ampl_resamp[:, item] = signal.resample(
            amplitude[:, item], int(len(amplitude)) * 10
        )  # resampling the amplitude vector
        # amp_peak = amp_peak + ampl_resamp[:, item] / volume.shape[2]

    fig, ax = plt.subplots(nrows=2, squeeze=True, figsize=(6, 8))

    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))

    ax[0].imshow(merge_vol, extent=extent, aspect="auto")
    ax[0].set_xlabel("x distance [mm]")
    ax[0].set_ylabel("y distance [mm]")

    ax[1].plot(y, amplitude, label="Amplitude profile")
    ax[1].set_ylabel("amplitude")
    ax[1].set_xlabel("y distance [mm]")
    ax[1].legend()
    fig.suptitle("Merged volume", fontsize=16)

    # peaks, peak_type, peak_figs = peak_find(ampl_resamp, dy)
    peaks, peak_type, peak_figs = pf.peak_find(ampl_resamp, dy)
    # junction_figs = minimize_junction_Y(ampl_resamp, peaks, peak_type, dy / 10)
    junction_figs = minY.minimize_junction_Y(ampl_resamp, peaks, peak_type, dy / 10)
    junctions.append(junction_figs)

    return fig, peak_figs, junctions


# this subroutine will merge the 4 jaws and analyze the two upper and two lower pairs
# each jaw is 6cm in length (60mm)
def merge_view_filtrot(volume, dx, dy):

    volume_resort = np.copy(
        volume
    )  # this will hold the resorted volume 0 to 3 clockwise
    junctions_comb = []
    peaks_figs_comb = []

    # we need to create 4 matches

    # 0,1,2,3 will be tagged top left, top right, bottom right, bottom left
    for i in range(0, int(np.shape(volume)[2])):
        diag_stack = [
            0,
            0,
            0,
            0,
        ]  # we will sum along one direction whichever is biggest will tag the file
        for j in range(0, int(min([np.shape(volume)[0], np.shape(volume)[1]]) / 2)):
            # print('j=',j,int(np.shape(volume)[0] / 2)+j, int(np.shape(volume)[1] / 2)+j)
            diag_stack[0] = (
                diag_stack[0]
                + volume[
                    int(np.shape(volume)[0] / 2) - j,
                    int(np.shape(volume)[1] / 2) - j,
                    i,
                ]
            )
            diag_stack[1] = (
                diag_stack[1]
                + volume[
                    int(np.shape(volume)[0] / 2) - j,
                    int(np.shape(volume)[1] / 2) + j,
                    i,
                ]
            )
            diag_stack[2] = (
                diag_stack[2]
                + volume[
                    int(np.shape(volume)[0] / 2) + j,
                    int(np.shape(volume)[1] / 2) + j,
                    i,
                ]
            )
            diag_stack[3] = (
                diag_stack[3]
                + volume[
                    int(np.shape(volume)[0] / 2) + j,
                    int(np.shape(volume)[1] / 2) - j,
                    i,
                ]
            )

        volume_resort[:, :, np.argmax(diag_stack)] = volume[:, :, i]

    # creating merged volumes
    merge_vol = np.zeros((volume_resort.shape[0], volume_resort.shape[1]))

    # creating vector for processing (1 horizontal & 1 vertical)
    amplitude_horz = np.zeros(
        (volume_resort.shape[1], volume_resort.shape[2])
    )  # 1 if it is vertical 0 if the bars are horizontal
    amplitude_vert = np.zeros((volume_resort.shape[0], volume_resort.shape[2]))

    # y = np.linspace(0, 0 + (volume_resort.shape[0] * dy), volume_resort.shape[0],
    #                 endpoint=False)  # definition of the distance axis
    # x = np.linspace(0, 0 + (volume_resort.shape[1] * dy), volume_resort.shape[1],
    #                 endpoint=False)  # definition of the distance axis

    ampl_resamp_y1 = np.zeros(
        ((volume_resort.shape[0]) * 10, int(volume_resort.shape[2] / 2))
    )
    ampl_resamp_y2 = np.zeros(
        ((volume_resort.shape[0]) * 10, int(volume_resort.shape[2] / 2))
    )

    ampl_resamp_x1 = np.zeros(
        ((volume_resort.shape[1]) * 10, int(volume_resort.shape[2] / 2))
    )
    ampl_resamp_x2 = np.zeros(
        ((volume_resort.shape[1]) * 10, int(volume_resort.shape[2] / 2))
    )

    amplitude_horz[:, 0] = volume_resort[
        int(volume_resort.shape[0] / 3.25), :, 0
    ]  # for profile 1
    amplitude_horz[:, 1] = volume_resort[
        int(volume_resort.shape[0] / 3.25), :, 1
    ]  # for profile 1
    amplitude_horz[:, 3] = volume_resort[
        int(volume_resort.shape[0]) - int(volume_resort.shape[0] / 3.25), :, 2
    ]  # the numbers here are reversed because we are going to slide the second graph (the overlay) to minimize the error  #for profile 2
    amplitude_horz[:, 2] = volume_resort[
        int(volume_resort.shape[0]) - int(volume_resort.shape[0] / 3.25), :, 3
    ]

    amplitude_vert[:, 0] = volume_resort[
        :, int(volume_resort.shape[1]) - int(volume_resort.shape[1] / 2.8), 1
    ]  # the numbers here are reversed because we are going to slide the second graph (the overlay) to minimize the error #for profile 3
    amplitude_vert[:, 1] = volume_resort[
        :, int(volume_resort.shape[1]) - int(volume_resort.shape[1] / 2.8), 2
    ]
    amplitude_vert[:, 3] = volume_resort[
        :, int(volume_resort.shape[1] / 2.8), 3
    ]  # for profile 4
    amplitude_vert[:, 2] = volume_resort[:, int(volume_resort.shape[1] / 2.8), 0]

    plt.figure()
    for item in tqdm(range(0, int(volume.shape[2] / 2))):
        merge_vol = merge_vol + volume[:, :, item]

        data_samp = amplitude_vert[:, item]
        ampl_resamp_y1[:, item] = signal.resample(
            data_samp, int(np.shape(amplitude_vert)[0]) * 10
        )
        data_samp = amplitude_horz[:, item]
        ampl_resamp_x1[:, item] = signal.resample(
            data_samp, int(np.shape(amplitude_horz)[0]) * 10
        )

    for item in tqdm(range(int(volume.shape[2] / 2), volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, item]
        data_samp = amplitude_vert[:, item]
        ampl_resamp_y2[:, item - int(volume.shape[2] / 2)] = signal.resample(
            data_samp, int(np.shape(amplitude_vert)[0]) * 10
        )
        data_samp = amplitude_horz[:, item]
        ampl_resamp_x2[:, item - int(volume.shape[2] / 2)] = signal.resample(
            data_samp, int(np.shape(amplitude_horz)[0]) * 10
        )

    fig, ax = plt.subplots(ncols=1, nrows=1, squeeze=True, figsize=(6, 8))

    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))

    ax.imshow(merge_vol, extent=extent, aspect="auto")
    ax.set_aspect("equal", "box")
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")
    fig.suptitle("Merged volume", fontsize=16)

    ax.hlines(dy * int(volume_resort.shape[0] / 3.25), 0, dx * volume_resort.shape[1])
    ax.text(
        dx * int(volume_resort.shape[1] / 2.25),
        dy * int(volume_resort.shape[0] / 3),
        "Profile 2",
    )

    ax.hlines(
        dy * int(volume_resort.shape[0]) - dy * int(volume_resort.shape[0] / 3.25),
        0,
        dx * volume_resort.shape[1],
    )
    ax.text(
        dx * int(volume_resort.shape[1] / 2.25),
        dy * int(volume_resort.shape[0]) - dy * int(volume_resort.shape[0] / 3.5),
        "Profile 1",
    )

    ax.vlines(dx * int(volume_resort.shape[1] / 2.8), 0, dy * volume_resort.shape[0])
    ax.text(
        dx * int(volume_resort.shape[1] / 3.1),
        dy * int(volume_resort.shape[0] / 1.8),
        "Profile 4",
        rotation=90,
    )

    ax.vlines(
        dx * int(volume_resort.shape[1]) - dx * int(volume_resort.shape[1] / 2.8),
        0,
        dy * volume_resort.shape[0],
    )
    ax.text(
        dx * int(volume_resort.shape[1]) - dx * int(volume_resort.shape[1] / 2.9),
        dy * int(volume_resort.shape[0] / 1.8),
        "Profile 3",
        rotation=90,
    )
    # plt.show()

    peaks, peak_type, peak_figs = pffr.peak_find_fieldrot(
        ampl_resamp_x1, dx, "Profile 1"
    )
    junction_figs = minFR.minimize_junction_fieldrot(
        ampl_resamp_x1, peaks, peak_type, dx / 10, "Profile 1"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = pffr.peak_find_fieldrot(
        ampl_resamp_x2, dx, "Profile 2"
    )
    junction_figs = minFR.minimize_junction_fieldrot(
        ampl_resamp_x2, peaks, peak_type, dx / 10, "Profile 2"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = pffr.peak_find_fieldrot(
        ampl_resamp_y1, dy, "Profile 3"
    )
    junction_figs = minFR.minimize_junction_fieldrot(
        ampl_resamp_y1, peaks, peak_type, dy / 10, "Profile 3"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = pffr.peak_find_fieldrot(
        ampl_resamp_y2, dy, "Profile 4"
    )
    junction_figs = minFR.minimize_junction_fieldrot(
        ampl_resamp_y2, peaks, peak_type, dy / 10, "Profile 4"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    return fig, peaks_figs_comb, junctions_comb


# this routine anlyzes the volume and autodetect the images and categorizes them for different tests
def image_analyze(volume, i_opt):
    xfield = []
    yfield = []
    rotfield = []

    if i_opt.startswith(("y", "yeah", "yes")):
        kx = 0
        ky = 0
        krot = 0
        for item in range(0, volume.shape[2]):
            stack1 = np.sum(
                volume[
                    int(
                        np.shape(volume)[0] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[0] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    int(
                        np.shape(volume)[1] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[1] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    item,
                ],
                axis=0,
            )
            maxstack1 = np.amax(stack1)

            # stack2 = np.sum(volume[:, :, item], axis=1)
            stack2 = np.sum(
                volume[
                    int(
                        np.shape(volume)[0] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[0] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    int(
                        np.shape(volume)[1] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[1] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    item,
                ],
                axis=1,
            )
            maxstack2 = np.amax(stack2)

            if maxstack2 / maxstack1 > 1.1:  # It is a Y field folder
                if ky == 0:
                    yfield = volume[:, :, item]
                    yfield = yfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, item]
                    yfield = np.append(yfield, volappend[:, :, np.newaxis], axis=2)
                ky = ky + 1
            elif maxstack2 / maxstack1 < 0.9:  # It is a X field folder
                if kx == 0:
                    xfield = volume[:, :, item]
                    xfield = xfield[:, :, np.newaxis]
                else:
                    # xfield=xfield[:,:,np.newaxis]
                    volappend = volume[:, :, item]
                    xfield = np.append(xfield, volappend[:, :, np.newaxis], axis=2)
                kx = kx + 1
            else:  # It is a field rotation folder
                if krot == 0:
                    rotfield = volume[:, :, item]
                    rotfield = rotfield[:, :, np.newaxis]
                else:
                    # rotfield = rotfield[:, :, np.newaxis]
                    volappend = volume[:, :, item]
                    rotfield = np.append(rotfield, volappend[:, :, np.newaxis], axis=2)
                krot = krot + 1

    else:
        kx = 0
        ky = 0
        krot = 0
        for item in range(0, volume.shape[2]):
            stack1 = np.sum(
                volume[
                    int(
                        np.shape(volume)[0] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[0] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    int(
                        np.shape(volume)[1] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[1] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    item,
                ],
                axis=0,
            )
            maxstack1 = np.amax(stack1)

            # stack2 = np.sum(volume[:, :, item], axis=1)
            stack2 = np.sum(
                volume[
                    int(
                        np.shape(volume)[0] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[0] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    int(
                        np.shape(volume)[1] / 2
                        - np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ) : int(
                        np.shape(volume)[1] / 2
                        + np.amin([np.shape(volume)[0], np.shape(volume)[1]]) / 2
                    ),
                    item,
                ],
                axis=1,
            )
            maxstack2 = np.amax(stack2)

            if maxstack2 / maxstack1 > 1.5:  # It is a Y field folder
                if ky == 0:
                    yfield = volume[:, :, item]
                    yfield = yfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, item]
                    yfield = np.append(yfield, volappend[:, :, np.newaxis], axis=2)
                ky = ky + 1
            elif maxstack2 / maxstack1 < 0.5:  # It is a X field folder
                if kx == 0:
                    xfield = volume[:, :, item]
                    xfield = xfield[:, :, np.newaxis]
                else:
                    # xfield=xfield[:,:,np.newaxis]
                    volappend = volume[:, :, item]
                    xfield = np.append(xfield, volappend[:, :, np.newaxis], axis=2)
                kx = kx + 1
            else:  # It is a field rotation folder
                if krot == 0:
                    rotfield = volume[:, :, item]
                    rotfield = rotfield[:, :, np.newaxis]
                else:
                    # rotfield = rotfield[:, :, np.newaxis]
                    volappend = volume[:, :, item]
                    rotfield = np.append(rotfield, volappend[:, :, np.newaxis], axis=2)
                krot = krot + 1

    return xfield, yfield, rotfield


# this routine anlyzes the volume and autodetect what type of analysis to carry on (x, Y, Field Rot)
def folder_analyze(volume):
    for item in range(0, volume.shape[2]):
        stack1 = np.sum(volume[:, :, item], axis=0)
        maxstack1 = np.max(stack1)

        stack2 = np.sum(volume[:, :, item], axis=1)
        maxstack2 = np.max(stack2)

        if maxstack2 / maxstack1 > 1.5:  # It is a Y field folder
            field = 2
        elif maxstack2 / maxstack1 < 0.5:  # It is a X field folder
            field = 1
        else:
            field = 3  # It is a field rotation folder

        return field


def read_dicom3D(direc, i_option):
    # item = 0
    for subdir, dirs, files in os.walk(direc):  # pylint: disable = unused-variable
        k = 0
        for file in tqdm(sorted(files)):
            # print('filename=', file)
            if os.path.splitext(file)[1] == ".dcm":
                dataset = pydicom.dcmread(direc + file)
                if k == 0:
                    ArrayDicom = np.zeros(
                        (dataset.Rows, dataset.Columns, 0),
                        dtype=dataset.pixel_array.dtype,
                    )
                    tmp_array = dataset.pixel_array
                    if i_option.startswith(("y", "yeah", "yes")):
                        max_val = np.amax(tmp_array)
                        tmp_array = tmp_array / max_val
                        min_val = np.amin(tmp_array)
                        tmp_array = tmp_array - min_val
                        tmp_array = 1 - tmp_array  # inverting the range

                        # min_val = np.amin(tmp_array)  # normalizing
                        # tmp_array = tmp_array - min_val
                        # tmp_array = tmp_array / (np.amax(tmp_array))
                        tmp_array = u.norm01(tmp_array)
                    else:
                        # min_val = np.amin(tmp_array)
                        # tmp_array = tmp_array - min_val
                        # tmp_array = tmp_array / (np.amax(tmp_array))
                        tmp_array = u.norm01(tmp_array)  # just normalize
                    ArrayDicom = np.dstack((ArrayDicom, tmp_array))
                    # print("item thickness [mm]=", dataset.SliceThickness)
                    SID = dataset.RTImageSID
                    dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                    dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                    print("pixel spacing row [mm]=", dx)
                    print("pixel spacing col [mm]=", dy)
                else:
                    tmp_array = dataset.pixel_array
                    if i_option.startswith(("y", "yeah", "yes")):
                        max_val = np.amax(tmp_array)
                        tmp_array = tmp_array / max_val
                        min_val = np.amin(tmp_array)
                        tmp_array = tmp_array - min_val
                        tmp_array = 1 - tmp_array  # inverting the range

                        # min_val = np.amin(tmp_array)  # normalizing
                        # tmp_array = tmp_array - min_val
                        # tmp_array = tmp_array / (np.amax(tmp_array))
                        tmp_array = u.norm01(tmp_array)
                    else:
                        # min_val = np.amin(tmp_array)
                        # tmp_array = tmp_array - min_val
                        # tmp_array = tmp_array / (np.amax(tmp_array))  # just normalize
                        tmp_array = u.norm01(tmp_array)
                    ArrayDicom = np.dstack((ArrayDicom, tmp_array))
            k = k + 1

    xfield, yfield, rotfield = image_analyze(ArrayDicom, i_option)

    multi_slice_viewer(ArrayDicom, dx, dy)

    if np.shape(xfield)[2] == 2:
        fig, peak_figs, junctions_figs = merge_view_vert(xfield, dx, dy)
        with PdfPages(direc + "jaws_X_report.pdf") as pdf:
            pdf.savefig(fig)
            # for i in range(0, len(peak_figs)):
            for _, f in enumerate(peak_figs):
                pdf.savefig(f)

            # for i in range(0, len(junctions_figs)):
            for _, f in enumerate(junctions_figs):
                pdf.savefig(f)

            plt.close()

    else:
        print(
            "X jaws data analysis not completed please verify that you have two X jaws images. For more information see manual."
        )

    if np.shape(yfield)[2] == 4:
        fig, peak_figs, junctions_figs = merge_view_horz(yfield, dx, dy)
        # print('peak_figs********************************************************=', len(peak_figs),peak_figs)
        with PdfPages(direc + "jaws_Y_report.pdf") as pdf:
            pdf.savefig(fig)
            # for i in range(0, len(peak_figs)):
            for _, f in enumerate(peak_figs):
                pdf.savefig(f)

            for _, f in enumerate(junctions_figs):
                pdf.savefig(f)

            plt.close()

    else:
        print(
            "Y jaws data analysis not completed please verify that you have four Y jaws images. For more information see manual."
        )

    if np.shape(rotfield)[2] == 4:
        fig, peak_figs, junctions_figs = merge_view_filtrot(rotfield, dx, dy)

        with PdfPages(direc + "jaws_FR_report.pdf") as pdf:
            pdf.savefig(fig)
            for _, f in enumerate(peak_figs):
                pdf.savefig(f)

            for _, f in enumerate(junctions_figs):
                pdf.savefig(f)

            plt.close()

    else:
        print(
            "Field rotation data analysis not completed please verify that you have four field rotation images. For more information see manual."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory", help="path to folder")
    args = parser.parse_args()

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Are these files from a clinac [yes(y)/no(n)]> ")
        try:
            ##        if line == 'done':
            ##            break
            ioption = str(line.lower())
            if ioption.startswith(("y", "yeah", "yes", "n", "no", "nope")):
                break

        except:  # pylint: disable = bare-except
            print("Please enter a valid option:")

    if args.directory:
        dirname = args.directory
        read_dicom3D(dirname, ioption)
