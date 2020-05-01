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
#   The folder should contain:
#   1 image at g=0, c=90
#   1 image at g=0, c=270
#   1 image at g=90, c=270
#   1 image at g=180, c=270
#   1 image at g=270, c=270
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-04-09
#
###########################################################################################

import argparse
import os
import sys
from math import sqrt
from operator import itemgetter

from tqdm import tqdm

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from PIL import Image
from skimage.feature import blob_log

import pydicom

from pymedphys.labs.pedromartinez.utils import utils as u


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
    for x, y in center:
        # ax.scatter(x,y)
        # ax.scatter(x*dx+dx/2,(volume.shape[0]-y)*dy-dy/2) #adding dx/2 and subtracting dy/2 correctly puts the point in the center of the pixel when using extents and not in the edge.
        ax.scatter(
            x * dx, (volume.shape[0] - y) * dy, label=title, color="k"
        )  # perfect!

    return fig, ax


def scalingAnalysis(ArrayDicom_o, dx, dy):  # determine scaling
    ArrayDicom = u.norm01(ArrayDicom_o)
    # ArrayDicom = norm01(ArrayDicom_o)
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
    img = ax.imshow(  # pylint: disable = unused-variable
        ArrayDicom_o, extent=extent, origin="lower"
    )
    # fig.colorbar(img, ax=ax, orientation="vertical")
    # img = ax.imshow(ArrayDicom_o)
    ax.set_xlabel("x distance [mm]")
    ax.set_ylabel("y distance [mm]")

    ax.scatter(point_sel[imax, 0] * dx, point_sel[imax, 1] * dy)
    ax.scatter(point_sel[imin, 0] * dx, point_sel[imin, 1] * dy)

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
    # ArrayDicom = norm01(ArrayDicom_o)
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
    # fig, ax = viewer(range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return fig, ax, center


def full_imageProcess_noGraph(ArrayDicom_o):  # process a full image
    ArrayDicom = u.norm01(ArrayDicom_o)
    # ArrayDicom = norm01(ArrayDicom_o)
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

    # fig, ax=viewer(range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return center


def point_detect_singleImage(imcirclist):
    detCenterXRegion = []
    detCenterYRegion = []

    print("Finding bibs in phantom...")
    grey_img = np.array(imcirclist, dtype=np.uint8)  # converting the image to grayscale
    blobs_log = blob_log(
        grey_img, min_sigma=15, max_sigma=50, num_sigma=10, threshold=0.05
    )
    # print(blobs_log)
    # exit(0)

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
        # radius = int(r)
        # print('center=', center, 'radius=', radius, 'value=', img[center], grey_img[center])

    xindx = int(centerXRegion[np.argmin(grey_ampRegion)])
    yindx = int(centerYRegion[np.argmin(grey_ampRegion)])
    # rindx = int(centerRRegion[np.argmin(grey_ampRegion)])

    detCenterXRegion = xindx
    detCenterYRegion = yindx

    return detCenterXRegion, detCenterYRegion


# def read_dicom(filename1,filename2,ioption):
def read_dicom(directory):
    for subdir, dirs, files in os.walk(directory):  # pylint: disable = unused-variable
        list_title = []
        list_gantry_angle = []
        list_collimator_angle = []
        list_figs = []
        # center_g0c90 = [(0, 0)]
        center_g0 = [(0, 0)]
        dx = 0
        dy = 0
        distance = 0  # pylint: disable = unused-variable

        k = 0  # we callect all the images in ArrayDicom
        for file in tqdm(sorted(files)):
            print(file)

            if os.path.splitext(directory + file)[1] == ".dcm":
                dataset = pydicom.dcmread(directory + file)
                gantry_angle = dataset[0x300A, 0x011E].value
                collimator_angle = dataset[0x300A, 0x0120].value

                list_gantry_angle.append(gantry_angle)
                list_collimator_angle.append(collimator_angle)

                # title = ('Gantry= ' + str(gantry_angle), 'Collimator= ' + str(collimator_angle))
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
                    # height = np.shape(ArrayDicom)[0]
                    # width = np.shape(ArrayDicom)[1]
                    SID = dataset.RTImageSID
                    dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                    dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                    print("pixel spacing row [mm]=", dx)
                    print("pixel spacing col [mm]=", dy)
                    distance, fig_scaling = scalingAnalysis(ArrayDicom, dx, dy)

                else:
                    list_title.append(title)
                    tmp_array = dataset.pixel_array
                    tmp_array = u.norm01(tmp_array)
                    # tmp_array = norm01(tmp_array)
                    ArrayDicom = np.dstack((ArrayDicom, tmp_array))

            k = k + 1

    # After we colect all the images we only select g0c90 and g0c270 to calculate the center at g0
    print(list_title)
    for i, _ in enumerate(list_title):
        if list_title[i][0] == "g0" and list_title[i][1] == "c90":
            # height = np.shape(ArrayDicom[:, :, i])[0]
            # width = np.shape(ArrayDicom[:, :, i])[1]
            fig_g0c90, ax_g0c90, center_g0c90 = full_imageProcess(
                ArrayDicom[:, :, i], dx, dy, list_title[i]
            )
            center_g0[0] = (
                center_g0[0][0] + center_g0c90[0][0] * 0.5,
                center_g0[0][1] + center_g0c90[0][1] * 0.5,
            )

            list_figs.append(fig_g0c90)  # we plot always the image at g0c90

        if list_title[i][0] == "g0" and list_title[i][1] == "c270":
            center_g0c270 = full_imageProcess_noGraph(ArrayDicom[:, :, i])
            center_g0[0] = (
                center_g0[0][0] + center_g0c270[0][0] * 0.5,
                center_g0[0][1] + center_g0c270[0][1] * 0.5,
            )

    # for i in range(0, len(list_title)):
    for i, _ in enumerate(list_title):
        if list_title[i][1] != "c90":
            center = full_imageProcess_noGraph(ArrayDicom[:, :, i])

            x_g0, y_g0 = center_g0[0]
            x, y = center[0]

            dist = sqrt(
                (x_g0 - x) * (x_g0 - x) * dx * dx + (y_g0 - y) * (y_g0 - y) * dy * dy
            )
            # dist = sqrt((width//2 - x) * (width//2 - x) * dx * dx + (height//2 - y) * (height//2 - y) * dy * dy)

            textstr = "offset" + str(list_title[i]) + "=" + str(round(dist, 4)) + " mm"

            ax_g0c90.scatter(
                x * dx, (ArrayDicom[:, :, i].shape[0] - y) * dy, label=textstr
            )  # perfect!

            print(list_title[i], "center_g0c90=", center_g0c90, "center=", center, dist)
            ax_g0c90.legend(bbox_to_anchor=(1.25, 1), loc=2, borderaxespad=0.0)

    with PdfPages(directory + "/" + "Graticule_report.pdf") as pdf:
        # Page = plt.figure(figsize=(4, 5))
        # Page.text(0, 0.9, 'Report', size=18)
        # Page.text(0, 0.9, "Distance=" + str(distance)+ " cm", size=14)
        pdf.savefig(fig_g0c90)
        pdf.savefig(fig_scaling)

    # exit(0)
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory", help="path to folder")
    args = parser.parse_args()

    if args.directory:
        dirname = args.directory
        read_dicom(dirname)
