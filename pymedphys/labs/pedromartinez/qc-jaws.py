# Copyright (C) 2019 Pedro Martinez

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


###########################################################################################
#
#   Script name: qc-jaws
#
#   Description: Tool for calculating jaws junction shifts for linear accelerators.
#   The script opens every DICOM file in a given folder and creates a combined profile
#   resulting from the superposition of the two or more fields. It then detects the
#   peak/through formed by the gap/overlap of the fields. A window is then selected
#   around this point and a Savitzky-Golay smoothing filter is then applied to the
#   combined profile. This new curve is then used iteratively to minimize the
#   profile created every time one of the profiles slide to close the gap or decrease
#   the overlap. The profile will achieve it greatest level of homogeneity when the
#   dosimetric penumbra of both fields are matched in space. The final result is the
#   optimal calculation of the gap/overlap between the two profiles. The software
#   generates a pdf file with a summary of all the results.
#
#   Example usage: python qc-jaws "/folder/"
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-04-09
#
###########################################################################################
# The following needs to be removed before leaving labs
# pylint: skip-file

import os
import subprocess
import sys

from tqdm import tqdm

import numpy as np
from scipy import signal
from scipy.signal import (
    butter,
    filtfilt,
    find_peaks,
    peak_prominences,
    peak_widths,
    savgol_filter,
)
from scipy.stats import linregress

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from PIL import *

import pydicom


def running_mean(x, N):
    out = np.zeros_like(x, dtype=np.float64)
    dim_len = x.shape[0]
    for i in range(dim_len):
        if N % 2 == 0:
            a, b = i - (N - 1) // 2, i + (N - 1) // 2 + 2
        else:
            a, b = i - (N - 1) // 2, i + (N - 1) // 2 + 1

        # cap indices to min and max indices
        a = max(0, a)
        b = min(dim_len, b)
        out[i] = np.mean(x[a:b])  # pylint: disable=unsupported-assignment-operation
    return out


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
    ax.set_title("slice=" + str(ax.index))
    fig.suptitle("Axial view", fontsize=16)
    fig.canvas.mpl_connect("key_press_event", process_key_axial)


def process_key_axial(event):
    fig = event.canvas.figure
    ax = fig.axes[0]
    if event.key == "j":
        previous_slice_axial(ax)
    elif event.key == "k":
        next_slice_axial(ax)
    ax.set_title("slice=" + str(ax.index))
    fig.canvas.draw()


def previous_slice_axial(ax):
    volume = ax.volume
    ax.index = (ax.index - 1) % volume.shape[2]  # wrap around using %
    print(ax.index, volume.shape[2])
    ax.images[0].set_array(volume[:, :, ax.index])


def next_slice_axial(ax):
    volume = ax.volume
    ax.index = (ax.index + 1) % volume.shape[2]
    print(ax.index, volume.shape[2])
    ax.images[0].set_array(volume[:, :, ax.index])


def minimize_junction_Y(amplitude, peaks, peak_type, dx):
    amp_prev = 0
    amp_filt_prev = 0

    fig = plt.figure(figsize=(10, 6))  # create the plot

    kk = 1  # counter for figure generation
    for j in range(0, amplitude.shape[1] - 1):
        for k in range(j + 1, amplitude.shape[1]):  # looping through remaining images
            amp_base_res = signal.savgol_filter(amplitude[:, j], 1001, 3)
            amp_overlay_res = signal.savgol_filter(amplitude[:, k], 1001, 3)
            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)

            if (
                abs(peak2 - peak1) < 2500
            ):  # if the two peaks are close together proceeed to analysis
                cumsum_prev = 1e7
                if peak2 < peak1:
                    amp_base_res = amplitude[:, k]
                    amp_overlay_res = amplitude[:, j]
                else:
                    amp_base_res = amplitude[:, j]
                    amp_overlay_res = amplitude[:, k]

                if (
                    peak_type[kk - 1] == 0
                ):  # kk-1 to start from the null element of the array
                    inc = -1
                else:
                    inc = 1
                for i in range(0, inc * 80, inc * 1):
                    # print('i', i)
                    x = np.linspace(
                        0, 0 + (len(amp_base_res) * dx), len(amplitude), endpoint=False
                    )  # definition of the distance axis
                    amp_overlay_res_roll = np.roll(amp_overlay_res, i)

                    # amplitude is the vector to analyze +-500 samples from the center
                    amp_tot = (
                        amp_base_res[peaks[kk - 1] - 1000 : peaks[kk - 1] + 1000]
                        + amp_overlay_res_roll[
                            peaks[kk - 1] - 1000 : peaks[kk - 1] + 1000
                        ]
                    )  # divided by 2 to normalize

                    xsel = x[peaks[kk - 1] - 1000 : peaks[kk - 1] + 1000]

                    amp_filt = running_mean(amp_tot, 281)
                    cumsum = np.sum(np.abs(amp_tot - amp_filt))

                    if cumsum > cumsum_prev:  # then we went too far
                        ax = fig.add_subplot(amplitude.shape[1] - 1, 1, kk)
                        ax.plot(amp_prev)
                        ax.plot(amp_filt_prev)
                        if kk == 1:
                            ax.set_title("Minimization result", fontsize=16)
                        if (
                            kk == amplitude.shape[1] - 1
                        ):  # if we reach the final plot the add the x axis label
                            ax.set_xlabel("distance [mm]")

                        ax.set_ylabel("amplitude")
                        ax.annotate(
                            "delta=" + str(abs(i - inc * 1) * dx) + " mm",
                            xy=(2, 1),
                            xycoords="axes fraction",
                            xytext=(0.35, 0.10),
                        )

                        kk = kk + 1
                        break
                    else:
                        amp_prev = amp_tot
                        amp_filt_prev = amp_filt
                        cumsum_prev = cumsum

            else:
                print(
                    j, k, "the data is not contiguous finding another curve in dataset"
                )

    return fig


def minimize_junction_X(amplitude, peaks, peak_type, dx):
    amp_prev = 0
    amp_filt_prev = 0

    fig = plt.figure(figsize=(10, 6))  # create the plot

    kk = 1  # counter for figure generation
    for j in range(0, amplitude.shape[1] - 1):
        for k in range(j + 1, amplitude.shape[1]):  # looping through remaining images
            amp_base_res = signal.savgol_filter(amplitude[:, j], 1001, 3)
            amp_overlay_res = signal.savgol_filter(amplitude[:, k], 1001, 3)
            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)

            if (
                abs(peak2 - peak1) < 2500
            ):  # if the two peaks are close together proceeed to analysis
                cumsum_prev = 1e7
                if peak2 < peak1:  # this guarantee that we always slide the overlay
                    amp_base_res = amplitude[:, k]
                    amp_overlay_res = amplitude[:, j]
                else:
                    amp_base_res = amplitude[:, j]
                    amp_overlay_res = amplitude[:, k]

                if peak_type[j] == 0:
                    inc = -1
                else:
                    inc = 1
                for i in range(0, inc * 80, inc * 1):
                    x = np.linspace(
                        0, 0 + (len(amp_base_res) * dx), len(amplitude), endpoint=False
                    )  # definition of the distance axis
                    amp_overlay_res_roll = np.roll(amp_overlay_res, i)

                    # amplitude is the vector to analyze +-500 samples from the center
                    amp_tot = (
                        amp_base_res[peaks[j] - 1000 : peaks[j] + 1000]
                        + amp_overlay_res_roll[peaks[j] - 1000 : peaks[j] + 1000]
                    )  # divided by 2 to normalize
                    xsel = x[peaks[j] - 1000 : peaks[j] + 1000]

                    amp_filt = running_mean(amp_tot, 281)
                    cumsum = np.sum(np.abs(amp_tot - amp_filt))

                    if cumsum > cumsum_prev:  # then we went too far
                        ax = fig.add_subplot(amplitude.shape[1] - 1, 1, kk)
                        ax.plot(amp_prev)
                        ax.plot(amp_filt_prev)
                        if kk == 1:
                            ax.set_title("Minimization result", fontsize=16)
                        if (
                            kk == amplitude.shape[1] - 1
                        ):  # if we reach the final plot the add the x axis label
                            ax.set_xlabel("distance [mm]")

                        ax.set_ylabel("amplitude")
                        ax.annotate(
                            "delta=" + str(abs(i - inc * 1) * dx) + " mm",
                            xy=(2, 1),
                            xycoords="axes fraction",
                            xytext=(0.35, 0.10),
                        )

                        kk = kk + 1
                        break
                    else:
                        amp_prev = amp_tot
                        amp_filt_prev = amp_filt
                        cumsum_prev = cumsum

            else:
                print(
                    j, k, "the data is not contiguous finding another curve in dataset"
                )

    return fig


# minimize junction for field rotations is done differently given the shape of the fields
def minimize_junction_fieldrot(amplitude, peaks, peak_type, dx, profilename):

    amp_prev = 0
    amp_filt_prev = 0

    fig = plt.figure(figsize=(10, 6))  # create the plot

    kk = 1  # counter for figure generation
    for j in range(0, amplitude.shape[1] - 1):
        for k in range(j + 1, amplitude.shape[1]):  # looping through remaining images
            amp_base_res = signal.savgol_filter(amplitude[:, j], 1001, 3)
            amp_overlay_res = signal.savgol_filter(amplitude[:, k], 1001, 3)
            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)

            cumsum_prev = 1e7
            amp_base_res = amplitude[:, j]
            amp_overlay_res = amplitude[:, k]

            if peak_type[j] == 0:
                inc = -1
            else:
                inc = 1
            for i in range(0, inc * 80, inc * 1):
                x = np.linspace(
                    0, 0 + (len(amp_base_res) * dx), len(amplitude), endpoint=False
                )  # definition of the distance axis
                amp_overlay_res_roll = np.roll(amp_overlay_res, i)

                amp_tot = (
                    amp_base_res[peaks[j] - 1000 : peaks[j] + 1000]
                    + amp_overlay_res_roll[peaks[j] - 1000 : peaks[j] + 1000]
                )  # divided by 2 to normalize
                xsel = x[peaks[j] - 1000 : peaks[j] + 1000]
                amp_filt = running_mean(amp_tot, 281)

                cumsum = np.sum(np.abs(amp_tot - amp_filt))

                if cumsum > cumsum_prev:  # then we went too far
                    ax = fig.add_subplot(amplitude.shape[1] - 1, 1, kk)

                    ax.plot(amp_prev)
                    ax.plot(amp_filt_prev)
                    if kk == 1:
                        ax.set_title(
                            "Minimization result - " + profilename, fontsize=16
                        )
                    if (
                        kk == amplitude.shape[1] - 1
                    ):  # if we reach the final plot the add the x axis label
                        ax.set_xlabel("distance [mm]")

                    ax.set_ylabel("amplitude")
                    ax.annotate(
                        "delta=" + str(abs(i - inc * 1) * dx) + " mm",
                        xy=(2, 1),
                        xycoords="axes fraction",
                        xytext=(0.35, 0.10),
                    )

                    kk = kk + 1
                    break
                else:
                    amp_prev = amp_tot
                    amp_filt_prev = amp_filt
                    cumsum_prev = cumsum

    return fig


# this subroutine aims to find the peaks
def peak_find(ampl_resamp, dx):
    peak_figs = []
    peaks = []
    peak_type = []
    for j in range(0, ampl_resamp.shape[1] - 1):
        amp_base_res = signal.savgol_filter(ampl_resamp[:, j], 1501, 1)
        for k in range(j + 1, ampl_resamp.shape[1]):
            amp_overlay_res = signal.savgol_filter(ampl_resamp[:, k], 1501, 1)

            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)

            if (
                abs(peak2 - peak1) < 2500
            ):  # if the two peaks are separated the two fields are not adjacent.
                amp_peak = ampl_resamp[:, j] + ampl_resamp[:, k]
                x = np.linspace(
                    0, 0 + (len(amp_peak) * dx / 10), len(amp_peak), endpoint=False
                )  # definition of the distance axis

                peak_pos, _ = find_peaks(
                    signal.savgol_filter(
                        amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )
                peak_neg, _ = find_peaks(
                    signal.savgol_filter(
                        -amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )

                if len(peak_pos) == 1 and len(peak_neg) != 1:
                    peak = peak_pos
                    peaks.append(min(peak1[0], peak2[0]) + peak[0])
                    peak_type.append(1)

                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(x, amp_peak, label="Total amplitude profile")
                    plt.plot(
                        x[min(peak1[0], peak2[0]) + peak[0]],
                        amp_peak[min(peak1[0], peak2[0]) + peak[0]],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions", fontsize=16)
                    peak_figs.append(fig)

                elif len(peak_pos) != 1 and len(peak_neg) == 1:
                    peak = peak_neg
                    peak_type.append(0)
                    peaks.append(min(peak1[0], peak2[0]) + peak[0])

                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(x, amp_peak, label="Total amplitude profile")
                    plt.plot(
                        x[min(peak1[0], peak2[0]) + peak[0]],
                        amp_peak[min(peak1[0], peak2[0]) + peak[0]],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions", fontsize=16)
                    peak_figs.append(fig)

                else:
                    peaks.append(0)
                    peak_type.append(0)
                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(x, amp_peak, label="Total amplitude profile")
                    plt.plot(
                        x[min(peak1[0], peak2[0])],
                        amp_peak[min(peak1[0], peak2[0])],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions", fontsize=16)
                    peak_figs.append(fig)

            else:
                print(
                    j, k, "the data is not contiguous finding another curve in dataset"
                )

    return peaks, peak_type, peak_figs


# this subroutine aims to find the peaks
def peak_find_fieldrot(ampl_resamp, dx, profilename):
    peaks = []
    peak_type = []
    for j in range(0, ampl_resamp.shape[1] - 1):
        amp_base_res = signal.savgol_filter(ampl_resamp[:, j], 1501, 1)
        for k in range(j + 1, ampl_resamp.shape[1]):
            amp_overlay_res = signal.savgol_filter(ampl_resamp[:, k], 1501, 1)

            peak1, _ = find_peaks(amp_base_res, prominence=0.5)
            peak2, _ = find_peaks(amp_overlay_res, prominence=0.5)
            # print('peak find', peak1, peak2, abs(peak2 - peak1))

            if (
                abs(peak2 - peak1) <= 4000
            ):  # if the two peaks are separated the two fields are not adjacent.
                amp_peak = (ampl_resamp[:, j] + ampl_resamp[:, k]) / 2
                x = np.linspace(
                    0, 0 + (len(amp_peak) * dx / 10), len(amp_peak), endpoint=False
                )  # definition of the distance axis

                peak_pos, _ = find_peaks(
                    signal.savgol_filter(
                        amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )
                peak_neg, _ = find_peaks(
                    signal.savgol_filter(
                        -amp_peak[min(peak1[0], peak2[0]) : max(peak1[0], peak2[0])],
                        201,
                        3,
                    ),
                    prominence=0.010,
                )

                if len(peak_pos) == 1 and len(peak_neg) != 1:
                    peak = peak_pos
                    # peak, _ = find_peaks(-amp_peak, prominence=1000)
                    peaks.append(min(peak1[0], peak2[0]) + peak[0])
                    peak_type.append(1)

                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(
                        x, amp_peak, label="Total amplitude profile - " + profilename
                    )
                    plt.plot(
                        x[min(peak1[0], peak2[0]) + peak[0]],
                        amp_peak[min(peak1[0], peak2[0]) + peak[0]],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions - " + profilename, fontsize=16)

                elif len(peak_pos) != 1 and len(peak_neg) == 1:
                    peak = peak_neg
                    peak_type.append(0)
                    peaks.append(min(peak1[0], peak2[0]) + peak[0])

                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(
                        x, amp_peak, label="Total amplitude profile - " + profilename
                    )
                    plt.plot(
                        x[min(peak1[0], peak2[0]) + peak[0]],
                        amp_peak[min(peak1[0], peak2[0]) + peak[0]],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions - " + profilename, fontsize=16)

                else:
                    peaks.append(0)
                    peak_type.append(0)
                    fig = plt.figure(figsize=(10, 6))
                    plt.plot(
                        x, amp_peak, label="Total amplitude profile - " + profilename
                    )
                    plt.plot(
                        x[min(peak1[0], peak2[0])],
                        amp_peak[min(peak1[0], peak2[0])],
                        "x",
                        label="Peaks detected",
                    )
                    plt.ylabel("amplitude [a.u.]")
                    plt.xlabel("distance [mm]")
                    plt.legend()
                    fig.suptitle("Junctions - " + profilename, fontsize=16)

            else:
                print(
                    j, k, "the data is not contiguous finding another curve in dataset"
                )

    return peaks, peak_type, fig


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

    # merging the two images together
    ampl_resamp = np.zeros(((volume.shape[1]) * 10, volume.shape[2]))

    for slice in tqdm(range(0, volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, slice]
        amplitude[:, slice] = volume[int(volume.shape[0] / 2), :, slice]
        ampl_resamp[:, slice] = signal.resample(
            amplitude[:, slice], int(len(amplitude)) * 10
        )  # resampling the amplitude vector

    fig, ax = plt.subplots(nrows=2, squeeze=True, figsize=(6, 8))

    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))

    ax[0].imshow(merge_vol, extent=extent)
    ax[0].set_xlabel("x distance [mm]")
    ax[0].set_ylabel("y distance [mm]")

    ax[1].plot(x, amplitude)
    ax[1].set_xlabel("x distance [mm]")
    ax[1].set_ylabel("amplitude")
    ax[1].legend()
    fig.suptitle("Merged volume", fontsize=16)

    peaks, peak_type, peak_figs = peak_find(ampl_resamp, dx)
    junction_figs = minimize_junction_X(ampl_resamp, peaks, peak_type, dx / 10)
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

    # merging the two images together
    ampl_resamp = np.zeros(((volume.shape[0]) * 10, volume.shape[2]))

    for slice in tqdm(range(0, volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, slice]
        amplitude[:, slice] = volume[:, int(volume.shape[1] / 2), slice]
        ampl_resamp[:, slice] = signal.resample(
            amplitude[:, slice], int(len(amplitude)) * 10
        )  # resampling the amplitude vector

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

    peaks, peak_type, peak_figs = peak_find(ampl_resamp, dy)
    junction_figs = minimize_junction_Y(ampl_resamp, peaks, peak_type, dy / 10)
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

    y = np.linspace(
        0, 0 + (volume_resort.shape[0] * dy), volume_resort.shape[0], endpoint=False
    )  # definition of the distance axis
    x = np.linspace(
        0, 0 + (volume_resort.shape[1] * dy), volume_resort.shape[1], endpoint=False
    )  # definition of the distance axis

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
    for slice in tqdm(range(0, int(volume.shape[2] / 2))):
        merge_vol = merge_vol + volume[:, :, slice]

        data_samp = amplitude_vert[:, slice]
        ampl_resamp_y1[:, slice] = signal.resample(
            data_samp, int(np.shape(amplitude_vert)[0]) * 10
        )
        data_samp = amplitude_horz[:, slice]
        ampl_resamp_x1[:, slice] = signal.resample(
            data_samp, int(np.shape(amplitude_horz)[0]) * 10
        )

    for slice in tqdm(range(int(volume.shape[2] / 2), volume.shape[2])):
        merge_vol = merge_vol + volume[:, :, slice]
        data_samp = amplitude_vert[:, slice]
        ampl_resamp_y2[:, slice - int(volume.shape[2] / 2)] = signal.resample(
            data_samp, int(np.shape(amplitude_vert)[0]) * 10
        )
        data_samp = amplitude_horz[:, slice]
        ampl_resamp_x2[:, slice - int(volume.shape[2] / 2)] = signal.resample(
            data_samp, int(np.shape(amplitude_horz)[0]) * 10
        )

    fig, ax = plt.subplots(ncols=1, nrows=1, squeeze=True, figsize=(6, 8))

    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))

    ax.imshow(merge_vol, extent=extent, aspect="auto")
    ax.set_aspect("equal", "box")
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")

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

    peaks, peak_type, peak_figs = peak_find_fieldrot(ampl_resamp_x1, dx, "Profile 1")
    junction_figs = minimize_junction_fieldrot(
        ampl_resamp_x1, peaks, peak_type, dx / 10, "Profile 1"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = peak_find_fieldrot(ampl_resamp_x2, dx, "Profile 2")
    junction_figs = minimize_junction_fieldrot(
        ampl_resamp_x2, peaks, peak_type, dx / 10, "Profile 2"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = peak_find_fieldrot(ampl_resamp_y1, dy, "Profile 3")
    junction_figs = minimize_junction_fieldrot(
        ampl_resamp_y1, peaks, peak_type, dy / 10, "Profile 3"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    peaks, peak_type, peak_figs = peak_find_fieldrot(ampl_resamp_y2, dy, "Profile 4")
    junction_figs = minimize_junction_fieldrot(
        ampl_resamp_y2, peaks, peak_type, dy / 10, "Profile 4"
    )
    peaks_figs_comb.append(peak_figs)
    junctions_comb.append(junction_figs)

    return fig, peaks_figs_comb, junctions_comb


# this routine anlyzes the volume and autodetect the images and categorizes them for different tests
def image_analyze(volume, ioption):
    xfield = []
    yfield = []
    rotfield = []

    if ioption.startswith(("y", "yeah", "yes")):
        max_val = np.amax(volume)
        volume = volume / max_val
        min_val = np.amin(volume)
        volume = volume - min_val
        volume = 1 - volume  # inverting the range

        min_val = np.amin(volume)  # normalizing
        volume = volume - min_val
        volume = volume / (np.amax(volume))

        # print('Volume shape=', np.shape(volume), np.amin([np.shape(volume)[0], np.shape(volume)[1]]))
        kx = 0
        ky = 0
        krot = 0
        for slice in range(0, volume.shape[2]):
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
                    slice,
                ],
                axis=0,
            )
            maxstack1 = np.amax(stack1)

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
                    slice,
                ],
                axis=1,
            )
            maxstack2 = np.amax(stack2)

            if maxstack2 / maxstack1 > 1.1:  # It is a Y field folder
                if ky == 0:
                    yfield = volume[:, :, slice]
                    yfield = yfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    yfield = np.append(yfield, volappend[:, :, np.newaxis], axis=2)
                ky = ky + 1
            elif maxstack2 / maxstack1 < 0.9:  # It is a X field folder
                if kx == 0:
                    xfield = volume[:, :, slice]
                    xfield = xfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    xfield = np.append(xfield, volappend[:, :, np.newaxis], axis=2)
                kx = kx + 1
            else:  # It is a field rotation folder
                if krot == 0:
                    rotfield = volume[:, :, slice]
                    rotfield = rotfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    rotfield = np.append(rotfield, volappend[:, :, np.newaxis], axis=2)
                krot = krot + 1

    else:
        min_val = np.amin(volume)
        volume = volume - min_val
        volume = volume / (np.amax(volume))
        kx = 0
        ky = 0
        krot = 0
        for slice in range(0, volume.shape[2]):
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
                    slice,
                ],
                axis=0,
            )
            maxstack1 = np.amax(stack1)

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
                    slice,
                ],
                axis=1,
            )
            maxstack2 = np.amax(stack2)

            if maxstack2 / maxstack1 > 1.5:  # It is a Y field folder
                if ky == 0:
                    yfield = volume[:, :, slice]
                    yfield = yfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    yfield = np.append(yfield, volappend[:, :, np.newaxis], axis=2)
                ky = ky + 1
            elif maxstack2 / maxstack1 < 0.5:  # It is a X field folder
                if kx == 0:
                    xfield = volume[:, :, slice]
                    xfield = xfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    xfield = np.append(xfield, volappend[:, :, np.newaxis], axis=2)
                kx = kx + 1
            else:  # It is a field rotation folder
                if krot == 0:
                    rotfield = volume[:, :, slice]
                    rotfield = rotfield[:, :, np.newaxis]
                else:
                    volappend = volume[:, :, slice]
                    rotfield = np.append(rotfield, volappend[:, :, np.newaxis], axis=2)
                krot = krot + 1

    return xfield, yfield, rotfield


# this routine anlyzes the volume and autodetect what type of analysis to carry on (x, Y, Field Rot)
def folder_analyze(volume):
    for slice in range(0, volume.shape[2]):
        stack1 = np.sum(volume[:, :, slice], axis=0)
        maxstack1 = np.max(stack1)

        stack2 = np.sum(volume[:, :, slice], axis=1)
        maxstack2 = np.max(stack2)

        if maxstack2 / maxstack1 > 1.5:  # It is a Y field folder
            return 2
        elif maxstack2 / maxstack1 < 0.5:  # It is a X field folder
            return 1
        else:
            return 3  # It is a field rotation folder


def read_dicom3D(dirname, poption, ioption):
    slice = 0
    # lstFilesDCM = [] #empty list to store dicom files
    for subdir, dirs, files in os.walk(dirname):
        k = 0
        for file in tqdm(sorted(files)):
            print("filename=", file)
            if os.path.splitext(file)[1] == ".dcm":
                if poption.startswith(("y", "yeah", "yes")):
                    subprocess.call(
                        [
                            "gdcmconv",
                            "-w",
                            dirname + file,
                            os.path.splitext(dirname + file)[0] + "_decomp" + ".dcm",
                        ]
                    )
                    dataset = pydicom.dcmread(
                        os.path.splitext(dirname + file)[0] + "_decomp" + ".dcm"
                    )
                    if k == 0:
                        ArrayDicom = np.zeros(
                            (dataset.Rows, dataset.Columns),
                            dtype=dataset.pixel_array.dtype,
                        )
                        ArrayDicom = np.dstack((ArrayDicom, dataset.pixel_array))
                        # print("slice thickness [mm]=",dataset.SliceThickness)
                        SID = dataset.RTImageSID
                        dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                        dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                        print("pixel spacing row [mm]=", dx)
                        print("pixel spacing col [mm]=", dy)
                    else:
                        ArrayDicom = np.dstack((ArrayDicom, dataset.pixel_array))
                elif poption.startswith(("n", "no", "nope")):
                    dataset = pydicom.dcmread(dirname + file)
                    if k == 0:
                        ArrayDicom = np.zeros(
                            (dataset.Rows, dataset.Columns, 0),
                            dtype=dataset.pixel_array.dtype,
                        )
                        ArrayDicom = np.dstack((ArrayDicom, dataset.pixel_array))
                        # print("slice thickness [mm]=", dataset.SliceThickness)
                        SID = dataset.RTImageSID
                        dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                        dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                        print("pixel spacing row [mm]=", dx)
                        print("pixel spacing col [mm]=", dy)
                    else:
                        ArrayDicom = np.dstack((ArrayDicom, dataset.pixel_array))
                print(k)
                k = k + 1

    xfield, yfield, rotfield = image_analyze(ArrayDicom, ioption)

    multi_slice_viewer(ArrayDicom, dx, dy)

    fig, peak_figs, junctions_figs = merge_view_vert(xfield, dx, dy)
    with PdfPages(dirname + "jaws_X_report.pdf") as pdf:
        pdf.savefig(fig)
        for i in range(0, len(peak_figs)):
            pdf.savefig(peak_figs[i])

        for i in range(0, len(junctions_figs)):
            pdf.savefig(junctions_figs[i])

        plt.close()

    fig, peak_figs, junctions_figs = merge_view_horz(yfield, dx, dy)
    with PdfPages(dirname + "jaws_Y_report.pdf") as pdf:
        pdf.savefig(fig)
        for i in range(0, len(peak_figs)):
            pdf.savefig(peak_figs[i])

        for i in range(0, len(junctions_figs)):
            pdf.savefig(junctions_figs[i])

        plt.close()

    fig, peak_figs, junctions_figs = merge_view_filtrot(rotfield, dx, dy)
    with PdfPages(dirname + "jaws_FR_report.pdf") as pdf:
        pdf.savefig(fig)
        for i in range(0, len(peak_figs)):
            pdf.savefig(peak_figs[i])

        for i in range(0, len(junctions_figs)):
            pdf.savefig(junctions_figs[i])

        plt.close()

    # Normal mode:
    print()
    print("Directory folder.........:", dirname)
    print("Storage type.....:", dataset.SOPClassUID)
    print()

    pat_name = dataset.PatientName
    display_name = pat_name.family_name + ", " + pat_name.given_name
    print("Patient's name...:", display_name)
    print("Patient id.......:", dataset.PatientID)
    print("Modality.........:", dataset.Modality)
    print("Study Date.......:", dataset.StudyDate)
    print("Gantry angle......", dataset.GantryAngle)


def main():
    try:
        dirname = str(sys.argv[1])
        print(dirname)
    except:
        print("Please enter a valid filename")
        print("Use the following command to run this script")
        print('python test_pydicom3D.py "[dirname]"')

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Are the files compressed [yes(y)/no(n)]> ")
        try:
            ##        if line == 'done':
            ##            break
            poption = str(line.lower())
            if poption.startswith(("y", "yeah", "yes", "n", "no", "nope")):
                break

        except:
            print("Please enter a valid option:")

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Are these files from a clinac [yes(y)/no(n)]> ")
        try:
            ##        if line == 'done':
            ##            break
            ioption = str(line.lower())
            if ioption.startswith(("y", "yeah", "yes", "n", "no", "nope")):
                break

        except:
            print("Please enter a valid option:")

    read_dicom3D(dirname, poption, ioption)


if __name__ == "__main__":
    main()
