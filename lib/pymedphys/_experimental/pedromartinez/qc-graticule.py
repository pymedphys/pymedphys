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
#   Script name: qc-graticule
#
#   Description: Tool for calculating graticule centre at different gantry angles.
#
#   Example usage: python qc-graticule "/folder/"
#
#   The folder can contain:
#   1/2 image(s) at g=0
#   1/2 image(s) at g=90
#   1/2 image(s) at g=180
#   1/2 image(s) at g=270
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2020-05-12
#
###########################################################################################

import argparse
import os
import sys
from datetime import datetime
from operator import itemgetter
from sys import platform

from tqdm import tqdm

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image
from skimage.feature import blob_log

import pydicom

from .utils import utils as u


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
        out[i] = np.mean(x[a:b])
    return out


# axial visualization and scrolling of the center points
def viewer(volume, dx, dy, center, title, textstr):
    print("center=", center)
    # remove_keymap_conflicts({'j', 'k'})
    fig = plt.figure(figsize=(12, 7))
    ax = fig.subplots()
    ax.volume = volume
    width = volume.shape[1]
    height = volume.shape[0]
    extent = (0, 0 + (volume.shape[1] * dx), 0, 0 + (volume.shape[0] * dy))
    img = ax.imshow(volume, extent=extent)
    # img=ax.imshow(volume)
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")
    # ax.set_xlabel('x pixel')
    # ax.set_ylabel('y pixel')
    ax.set_xlim(width * dx / 2 - 10, width * dx / 2 + 10)
    ax.set_ylim(height * dy / 2 - 10, height * dy / 2 + 10)

    # fig.suptitle('Image', fontsize=16)
    print(title[0])
    ax.set_title(title[0] + "\n" + title[1], fontsize=16)
    ax.text((volume.shape[1] + 250) * dx, (volume.shape[0]) * dy, textstr)
    fig.subplots_adjust(right=0.75)
    fig.colorbar(img, ax=ax, orientation="vertical")
    # fig.canvas.mpl_connect('key_press_event', process_key_axial)

    return fig, ax


def scalingAnalysis(ArrayDicom_o, dx, dy):  # determine scaling
    ArrayDicom = u.norm01(ArrayDicom_o)
    blobs_log = blob_log(
        ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20, threshold=0.15
    )  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(
        point_det, key=itemgetter(2), reverse=True
    )  # here we sort by the radius of the dot bigger dots are around the center and edges

    point_det = np.asarray(point_det)

    # now we need to select the most extreme left and right point
    print(np.shape(ArrayDicom)[0] // 2)
    print(abs(point_det[:6, 1] - np.shape(ArrayDicom)[0] // 2) < 10)
    point_sel = []
    for i in range(0, 6):
        if abs(point_det[i, 1] - np.shape(ArrayDicom)[0] // 2) < 10:
            point_sel.append(abs(point_det[i, :]))

    point_sel = np.asarray(point_sel)

    imax = np.argmax(point_sel[:, 0])
    imin = np.argmin(point_sel[:, 0])

    print(point_sel[imax, :], point_sel[imin, :])
    distance = (
        np.sqrt(
            (point_sel[imax, 0] - point_sel[imin, 0])
            * (point_sel[imax, 0] - point_sel[imin, 0])
            * dx
            * dx
            + (point_sel[imax, 1] - point_sel[imin, 1])
            * (point_sel[imax, 1] - point_sel[imin, 1])
            * dy
            * dy
        )
        / 10.0
    )

    print("distance=", distance, "cm")  # distance is reported in cm

    # plotting the figure of scaling results

    fig = plt.figure(figsize=(12, 7))
    ax = fig.subplots()
    ax.volume = ArrayDicom_o
    width = ArrayDicom_o.shape[1]
    height = ArrayDicom_o.shape[0]
    extent = (0, 0 + (width * dx), 0, 0 + (height * dy))
    img = ax.imshow(ArrayDicom_o, extent=extent, origin="lower")
    # img = ax.imshow(ArrayDicom_o)
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")

    ax.scatter(point_sel[imax, 0] * dx, point_sel[imax, 1] * dy)
    ax.scatter(point_sel[imin, 0] * dx, point_sel[imin, 1] * dy)
    fig.colorbar(img, ax=ax, orientation="vertical")

    # adding a horizontal arrow
    ax.annotate(
        s="",
        xy=(point_sel[imax, 0] * dx, point_sel[imax, 1] * dy),
        xytext=(point_sel[imin, 0] * dx, point_sel[imin, 1] * dy),
        arrowprops=dict(arrowstyle="<->", color="r"),
    )  # example on how to plot a double headed arrow
    ax.text(
        (width // 2.8) * dx,
        (height // 2 + 10) * dy,
        "Distance=" + str(round(distance, 4)) + " cm",
        rotation=0,
        fontsize=14,
        color="r",
    )

    return distance, fig


def full_imageProcess(ArrayDicom_o, dx, dy, title):  # process a full image
    ArrayDicom = u.norm01(ArrayDicom_o)
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]

    blobs_log = blob_log(
        ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20, threshold=0.15
    )  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    center = []
    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(
        point_det, key=itemgetter(2), reverse=True
    )  # here we sort by the radius of the dot bigger dots are around the center and edges

    # we need to find the centre dot as well as the larger dots on the sides of the image

    # for j in range(0, len(point_det)):
    #     x, y, r = point_det[j]
    #     center.append((int(round(x)), int(round(y))))

    # now that we have detected the centre we are going to increase the precision of the detected point
    im_centre = Image.fromarray(
        255
        * ArrayDicom[
            height // 2 - 20 : height // 2 + 20, width // 2 - 20 : width // 2 + 20
        ]
    )
    im_centre = im_centre.resize(
        (im_centre.width * 10, im_centre.height * 10), Image.LANCZOS
    )

    xdet_int, ydet_int = point_detect_singleImage(im_centre)
    xdet = int(width // 2 - 20) + xdet_int / 10
    ydet = int(height // 2 - 20) + ydet_int / 10

    center.append((xdet, ydet))

    textstr = ""

    print("center=", center)
    fig, ax = viewer(u.range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return fig, ax, center


def full_imageProcess_noGraph(ArrayDicom_o):  # process a full image
    ArrayDicom = u.norm01(ArrayDicom_o)
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]

    blobs_log = blob_log(
        ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20, threshold=0.15
    )  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    center = []
    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(
        point_det, key=itemgetter(2), reverse=True
    )  # here we sort by the radius of the dot bigger dots are around the center and edges

    # we need to find the centre dot as well as the larger dots on the sides of the image

    # for j in range(0, len(point_det)):
    #     x, y, r = point_det[j]
    #     center.append((int(round(x)), int(round(y))))

    # now that we have detected the centre we are going to increase the precision of the detected point
    im_centre = Image.fromarray(
        255
        * ArrayDicom[
            height // 2 - 20 : height // 2 + 20, width // 2 - 20 : width // 2 + 20
        ]
    )
    im_centre = im_centre.resize(
        (im_centre.width * 10, im_centre.height * 10), Image.LANCZOS
    )

    xdet_int, ydet_int = point_detect_singleImage(im_centre)
    xdet = int(width // 2 - 20) + xdet_int / 10
    ydet = int(height // 2 - 20) + ydet_int / 10

    center.append((xdet, ydet))

    # fig, ax=viewer(u.range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return center


def point_detect_singleImage(imcirclist):
    detCenterXRegion = []
    detCenterYRegion = []

    print("Finding bibs in phantom...")
    grey_img = np.array(imcirclist, dtype=np.uint8)  # converting the image to grayscale
    blobs_log = blob_log(
        grey_img, min_sigma=15, max_sigma=50, num_sigma=10, threshold=0.05
    )

    centerXRegion = []
    centerYRegion = []
    centerRRegion = []
    grey_ampRegion = []
    for blob in blobs_log:
        y, x, r = blob
        # center = (int(x), int(y))
        centerXRegion.append(x)
        centerYRegion.append(y)
        centerRRegion.append(r)
        grey_ampRegion.append(grey_img[int(y), int(x)])

    xindx = int(centerXRegion[np.argmin(grey_ampRegion)])
    yindx = int(centerYRegion[np.argmin(grey_ampRegion)])
    # rindx = int(centerRRegion[np.argmin(grey_ampRegion)])

    detCenterXRegion = xindx
    detCenterYRegion = yindx

    return detCenterXRegion, detCenterYRegion


# def read_dicom(filename1,filename2,ioption):
def read_dicom(directory):
    now = datetime.now()
    for subdir, dirs, files in os.walk(directory):  # pylint: disable = unused-variable
        dirs.clear()
        list_title = []
        list_gantry_angle = []
        list_collimator_angle = []
        list_figs = []
        center = []
        center_g0 = [(0, 0)]
        center_g90 = [(0, 0)]
        center_g180 = [(0, 0)]
        center_g270 = [(0, 0)]
        dx = 0
        dy = 0

        k = 0  # we callect all the images in ArrayDicom
        for file in tqdm(sorted(files)):
            print("Reading file=>", file)

            if os.path.splitext(directory + file)[1] == ".dcm":
                dataset = pydicom.dcmread(directory + file)
                gantry_angle = dataset[0x300A, 0x011E].value
                collimator_angle = dataset[0x300A, 0x0120].value

                list_gantry_angle.append(gantry_angle)
                list_collimator_angle.append(collimator_angle)

                if round(gantry_angle) == 360:
                    gantry_angle = 0
                if round(collimator_angle) == 360:
                    collimator_angle = 0

                title = (
                    "g" + str(round(gantry_angle)),
                    "c" + str(round(collimator_angle)),
                )
                print(title)

                if k == 0:
                    # title = ('Gantry= ' + str(gantry_angle), 'Collimator= ' + str(collimator_angle))
                    title = (
                        "g" + str(round(gantry_angle)),
                        "c" + str(round(collimator_angle)),
                    )
                    list_title.append(title)
                    ArrayDicom = dataset.pixel_array
                    height = np.shape(ArrayDicom)[0]
                    width = np.shape(ArrayDicom)[1]
                    SID = dataset.RTImageSID
                    dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                    dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                    print("pixel spacing row [mm]=", dx)
                    print("pixel spacing col [mm]=", dy)
                    distance, fig_scaling = scalingAnalysis(ArrayDicom, dx, dy)
                    print("distance", distance)

                else:
                    list_title.append(title)
                    tmp_array = dataset.pixel_array
                    tmp_array = u.norm01(tmp_array)
                    ArrayDicom = np.dstack((ArrayDicom, tmp_array))

                k = k + 1

    # After we colect all the images we only select g0c90 and g0c270 to calculate the center at g0

    k = 0
    l = 0
    m = 0
    n = 0

    for i, _ in enumerate(list_title):
        if list_title[i][0] == "g0" and k == 0:
            k = k + 1
            # height = np.shape(ArrayDicom[:, :, i])[0]
            # width = np.shape(ArrayDicom[:, :, i])[1]
            fig_g0c90, ax_g0c90, center_g0c90 = full_imageProcess(
                ArrayDicom[:, :, i], dx, dy, list_title[i]
            )
            center_g0[0] = (
                center_g0[0][0] + center_g0c90[0][0],
                center_g0[0][1] + center_g0c90[0][1],
            )

            list_figs.append(fig_g0c90)  # we plot always the image at g0c90

        if list_title[i][0] == "g0" and k != 0:
            k = k + 1
            center_g0c270 = full_imageProcess_noGraph(ArrayDicom[:, :, i])
            center_g0[0] = (
                center_g0[0][0] + center_g0c270[0][0],
                center_g0[0][1] + center_g0c270[0][1],
            )

    for i, _ in enumerate(list_title):
        if list_title[i][0] == "g90":
            l = l + 1
            center_g90c = full_imageProcess_noGraph(ArrayDicom[:, :, i])
            center_g90[0] = (
                center_g90[0][0] + center_g90c[0][0],
                center_g90[0][1] + center_g90c[0][1],
            )

        if list_title[i][0] == "g180":
            m = m + 1
            center_g180c = full_imageProcess_noGraph(ArrayDicom[:, :, i])
            center_g180[0] = (
                center_g180[0][0] + center_g180c[0][0],
                center_g180[0][1] + center_g180c[0][1],
            )

        if list_title[i][0] == "g270":
            n = n + 1
            center_g270c = full_imageProcess_noGraph(ArrayDicom[:, :, i])
            center_g270[0] = (
                center_g270[0][0] + center_g270c[0][0],
                center_g270[0][1] + center_g270c[0][1],
            )

    print(k, "images used for g0")
    print(l, "images used for g90")
    print(m, "images used for g180")
    print(n, "images used for g270")

    center_g0[0] = (center_g0[0][0] / k, center_g0[0][1] / k)
    center_g90[0] = (center_g90[0][0] / l, center_g90[0][1] / l)
    center_g180[0] = (center_g180[0][0] / m, center_g180[0][1] / m)
    center_g270[0] = (center_g270[0][0] / n, center_g270[0][1] / n)

    center.append(center_g0[0])
    center.append(center_g90[0])
    center.append(center_g180[0])
    center.append(center_g270[0])

    x_g0, y_g0 = center_g0[0]
    x_g90, y_g90 = center_g90[0]
    x_g180, y_g180 = center_g180[0]
    x_g270, y_g270 = center_g270[0]

    max_deltax = 0
    max_deltay = 0
    for i in range(0, len(center)):  # pylint: disable = consider-using-enumerate
        for j in range(i + 1, len(center)):
            deltax = abs(center[i][0] - center[j][0])
            deltay = abs(center[i][1] - center[j][1])
            if deltax > max_deltax:
                max_deltax = deltax
            if deltay > max_deltay:
                max_deltay = deltay

    print("Maximum delta x =", max_deltax * dx, "mm")
    print("Maximum delta y =", max_deltay * dy, "mm")

    ax_g0c90.scatter(
        x_g0 * dx, (ArrayDicom[:, :, i].shape[0] - y_g0) * dy, label="g=0"
    )  # perfect!

    ax_g0c90.scatter(
        x_g90 * dx, (ArrayDicom[:, :, i].shape[0] - y_g90) * dy, label="g=90"
    )  # perfect!
    ax_g0c90.scatter(
        x_g180 * dx, (ArrayDicom[:, :, i].shape[0] - y_g180) * dy, label="g=180"
    )  # perfect!
    ax_g0c90.scatter(
        x_g270 * dx, (ArrayDicom[:, :, i].shape[0] - y_g270) * dy, label="g=270"
    )  # perfect!

    # print(list_title[i], "center_g0c90=", center_g0c90, "center=", center, dist)
    ax_g0c90.legend(bbox_to_anchor=(1.25, 1), loc=2, borderaxespad=0.0)

    # adding a horizontal arrow
    # ax.annotate(
    #     s="",
    #     xy=(point_sel[imax, 0] * dx, point_sel[imax, 1] * dy),
    #     xytext=(point_sel[imin, 0] * dx, point_sel[imin, 1] * dy),
    #     arrowprops=dict(arrowstyle="<->", color="r"),
    # )  # example on how to plot a double headed arrow
    ax_g0c90.text(
        (width // 2.15) * dx,
        (height // 2.15) * dy,
        "Maximum delta x =" + str(round(max_deltax * dx, 4)) + " mm",
        rotation=0,
        fontsize=14,
        color="r",
    )
    ax_g0c90.text(
        (width // 2.15) * dx,
        (height // 2.18) * dy,
        "Maximum delta y =" + str(round(max_deltay * dy, 4)) + " mm",
        rotation=0,
        fontsize=14,
        color="r",
    )

    if platform == "linux":
        output_flnm = (
            dirname
            + "/"
            + now.strftime("%d-%m-%Y_%H:%M_")
            + dataset[0x0008, 0x1010].value
            + "_Graticule_report.pdf"
        )
    elif platform == "win32":
        output_flnm = dataset[0x0008, 0x1010].value + "_Graticule_report.pdf"

    # with PdfPages(directory + "/" + output_flnm) as pdf:
    with PdfPages(output_flnm) as pdf:
        # Page = plt.figure(figsize=(4, 5))
        # Page.text(0, 0.9, 'Report', size=18)
        # Page.text(0, 0.9, "Distance=" + str(distance)+ " cm", size=14)
        pdf.savefig(fig_g0c90)
        pdf.savefig(fig_scaling)

    # exit(0)
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()  # pylint: disable = invalid-name
    parser.add_argument("-d", "--directory", help="path to folder")
    args = parser.parse_args()  # pylint: disable = invalid-name

    if args.directory:
        dirname = args.directory  # pylint: disable = invalid-name
        read_dicom(dirname)
