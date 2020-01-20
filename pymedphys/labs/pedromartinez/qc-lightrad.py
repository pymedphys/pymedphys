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
#   Example usage: python qc-lightrad "/file/"
#
#   Using MED-TEC MT-IAD-1 phantom
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-04-09
#
###########################################################################################

import argparse
import os
from datetime import datetime

from tqdm import tqdm

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from PIL import Image
from skimage.feature import blob_log

import pydicom

from pymedphys.labs.pedromartinez.utils import utils as u


def point_detect(imcirclist):
    k = 0
    detCenterXRegion = []
    detCenterYRegion = []

    print("Finding bibs in phantom...")
    for img in tqdm(imcirclist):
        grey_img = np.array(img, dtype=np.uint8)  # converting the image to grayscale
        blobs_log = blob_log(
            grey_img, min_sigma=15, max_sigma=40, num_sigma=10, threshold=0.05
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
            # radius = int(r)
            # print('center=', center, 'radius=', radius, 'value=', img[center], grey_img[center])

        xindx = int(centerXRegion[np.argmin(grey_ampRegion)])
        yindx = int(centerYRegion[np.argmin(grey_ampRegion)])
        # rindx = int(centerRRegion[np.argmin(grey_ampRegion)])

        detCenterXRegion.append(xindx)
        detCenterYRegion.append(yindx)

        k = k + 1

    return detCenterXRegion, detCenterYRegion


def read_dicom(filenm, ioptn):
    dataset = pydicom.dcmread(filenm)
    now = datetime.now()

    ArrayDicom = np.zeros(
        (dataset.Rows, dataset.Columns), dtype=dataset.pixel_array.dtype
    )
    ArrayDicom = dataset.pixel_array
    SID = dataset.RTImageSID
    print("array_shape=", np.shape(ArrayDicom))
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]
    dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
    dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
    print("pixel spacing row [mm]=", dx)
    print("pixel spacing col [mm]=", dy)

    # creating the figure extent based on the image dimensions, we divide by 10 to get the units in cm
    extent = (
        0,
        0 + (ArrayDicom.shape[1] * dx / 10),
        0 + (ArrayDicom.shape[0] * dy / 10),
        0,
    )

    # creating the figure extent list for the bib images
    list_extent = []

    # plt.figure()
    # plt.imshow(ArrayDicom, extent=extent, origin='upper')
    # plt.imshow(ArrayDicom)
    # plt.xlabel('x distance [cm]')
    # plt.ylabel('y distance [cm]')
    # plt.show()

    if ioptn.startswith(("y", "yeah", "yes")):
        height, width = ArrayDicom.shape
        ArrayDicom_mod = ArrayDicom[
            :, width // 2 - height // 2 : width // 2 + height // 2
        ]
    else:
        ArrayDicom_mod = ArrayDicom

    # we take a diagonal profile to avoid phantom artifacts
    # im_profile = ArrayDicom_mod.diagonal()

    # test to make sure image is displayed correctly bibs are high amplitude against dark background
    ctr_pixel = ArrayDicom_mod[height // 2, width // 2]
    corner_pixel = ArrayDicom_mod[0, 0]

    if ctr_pixel > corner_pixel:
        ArrayDicom = u.range_invert(ArrayDicom)

    ArrayDicom = u.norm01(ArrayDicom)

    # working on transforming the full image and invert it first and go from there.
    if ioptn.startswith(("y", "yeah", "yes")):
        ROI1 = {"edge_top": 70, "edge_bottom": 130, "edge_left": 270, "edge_right": 350}
        ROI2 = {"edge_top": 70, "edge_bottom": 130, "edge_left": 680, "edge_right": 760}
        ROI3 = {
            "edge_top": 150,
            "edge_bottom": 210,
            "edge_left": 760,
            "edge_right": 830,
        }
        ROI4 = {
            "edge_top": 560,
            "edge_bottom": 620,
            "edge_left": 760,
            "edge_right": 830,
        }
        ROI5 = {
            "edge_top": 640,
            "edge_bottom": 700,
            "edge_left": 680,
            "edge_right": 760,
        }
        ROI6 = {
            "edge_top": 640,
            "edge_bottom": 700,
            "edge_left": 270,
            "edge_right": 350,
        }
        ROI7 = {
            "edge_top": 560,
            "edge_bottom": 620,
            "edge_left": 200,
            "edge_right": 270,
        }
        ROI8 = {
            "edge_top": 150,
            "edge_bottom": 210,
            "edge_left": 200,
            "edge_right": 270,
        }
    else:
        ROI1 = {
            "edge_top": 280,
            "edge_bottom": 360,
            "edge_left": 360,
            "edge_right": 440,
        }
        ROI2 = {
            "edge_top": 280,
            "edge_bottom": 360,
            "edge_left": 830,
            "edge_right": 910,
        }
        ROI3 = {
            "edge_top": 360,
            "edge_bottom": 440,
            "edge_left": 940,
            "edge_right": 1020,
        }
        ROI4 = {
            "edge_top": 840,
            "edge_bottom": 920,
            "edge_left": 940,
            "edge_right": 1020,
        }
        ROI5 = {
            "edge_top": 930,
            "edge_bottom": 1000,
            "edge_left": 830,
            "edge_right": 910,
        }
        ROI6 = {
            "edge_top": 930,
            "edge_bottom": 1000,
            "edge_left": 360,
            "edge_right": 440,
        }
        ROI7 = {
            "edge_top": 840,
            "edge_bottom": 920,
            "edge_left": 280,
            "edge_right": 360,
        }
        ROI8 = {
            "edge_top": 360,
            "edge_bottom": 440,
            "edge_left": 280,
            "edge_right": 360,
        }

    # images for object detection
    imcirclist = []
    imcirc1 = Image.fromarray(
        255
        * ArrayDicom[
            ROI1["edge_top"] : ROI1["edge_bottom"],
            ROI1["edge_left"] : ROI1["edge_right"],
        ]
    )
    imcirc1 = imcirc1.resize((imcirc1.width * 10, imcirc1.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI1["edge_left"] * dx / 10),
            (ROI1["edge_right"] * dx / 10),
            (ROI1["edge_bottom"] * dy / 10),
            (ROI1["edge_top"] * dy / 10),
        )
    )

    imcirc2 = Image.fromarray(
        255
        * ArrayDicom[
            ROI2["edge_top"] : ROI2["edge_bottom"],
            ROI2["edge_left"] : ROI2["edge_right"],
        ]
    )
    imcirc2 = imcirc2.resize((imcirc2.width * 10, imcirc2.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI2["edge_left"] * dx / 10),
            (ROI2["edge_right"] * dx / 10),
            (ROI2["edge_bottom"] * dy / 10),
            (ROI2["edge_top"] * dy / 10),
        )
    )

    imcirc3 = Image.fromarray(
        255
        * ArrayDicom[
            ROI3["edge_top"] : ROI3["edge_bottom"],
            ROI3["edge_left"] : ROI3["edge_right"],
        ]
    )
    imcirc3 = imcirc3.resize((imcirc3.width * 10, imcirc3.height * 10), Image.LANCZOS)
    list_extent.append(
        (
            (ROI3["edge_left"] * dx / 10),
            (ROI3["edge_right"] * dx / 10),
            (ROI3["edge_bottom"] * dy / 10),
            (ROI3["edge_top"] * dy / 10),
        )
    )

    imcirc4 = Image.fromarray(
        255
        * ArrayDicom[
            ROI4["edge_top"] : ROI4["edge_bottom"],
            ROI4["edge_left"] : ROI4["edge_right"],
        ]
    )
    imcirc4 = imcirc4.resize((imcirc4.width * 10, imcirc4.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI4["edge_left"] * dx / 10),
            (ROI4["edge_right"] * dx / 10),
            (ROI4["edge_bottom"] * dy / 10),
            (ROI4["edge_top"] * dy / 10),
        )
    )

    imcirc5 = Image.fromarray(
        255
        * ArrayDicom[
            ROI5["edge_top"] : ROI5["edge_bottom"],
            ROI5["edge_left"] : ROI5["edge_right"],
        ]
    )
    imcirc5 = imcirc5.resize((imcirc5.width * 10, imcirc5.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI5["edge_left"] * dx / 10),
            (ROI5["edge_right"] * dx / 10),
            (ROI5["edge_bottom"] * dy / 10),
            (ROI5["edge_top"] * dy / 10),
        )
    )

    imcirc6 = Image.fromarray(
        255
        * ArrayDicom[
            ROI6["edge_top"] : ROI6["edge_bottom"],
            ROI6["edge_left"] : ROI6["edge_right"],
        ]
    )
    imcirc6 = imcirc6.resize((imcirc6.width * 10, imcirc6.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI6["edge_left"] * dx / 10),
            (ROI6["edge_right"] * dx / 10),
            (ROI6["edge_bottom"] * dy / 10),
            (ROI6["edge_top"] * dy / 10),
        )
    )

    imcirc7 = Image.fromarray(
        255
        * ArrayDicom[
            ROI7["edge_top"] : ROI7["edge_bottom"],
            ROI7["edge_left"] : ROI7["edge_right"],
        ]
    )
    imcirc7 = imcirc7.resize((imcirc7.width * 10, imcirc7.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI7["edge_left"] * dx / 10),
            (ROI7["edge_right"] * dx / 10),
            (ROI7["edge_bottom"] * dy / 10),
            (ROI7["edge_top"] * dy / 10),
        )
    )

    imcirc8 = Image.fromarray(
        255
        * ArrayDicom[
            ROI8["edge_top"] : ROI8["edge_bottom"],
            ROI8["edge_left"] : ROI8["edge_right"],
        ]
    )
    imcirc8 = imcirc8.resize((imcirc8.width * 10, imcirc8.height * 10), Image.LANCZOS)

    list_extent.append(
        (
            (ROI8["edge_left"] * dx / 10),
            (ROI8["edge_right"] * dx / 10),
            (ROI8["edge_bottom"] * dy / 10),
            (ROI8["edge_top"] * dy / 10),
        )
    )

    imcirclist.append(imcirc1)
    imcirclist.append(imcirc2)
    imcirclist.append(imcirc3)
    imcirclist.append(imcirc4)
    imcirclist.append(imcirc5)
    imcirclist.append(imcirc6)
    imcirclist.append(imcirc7)
    imcirclist.append(imcirc8)

    xdet, ydet = point_detect(imcirclist)

    profiles = []
    profile1 = np.array(imcirc1, dtype=np.uint8)[:, xdet[0]] / 255
    profile2 = np.array(imcirc2, dtype=np.uint8)[:, xdet[1]] / 255
    profile3 = np.array(imcirc3, dtype=np.uint8)[ydet[2], :] / 255
    profile4 = np.array(imcirc4, dtype=np.uint8)[ydet[3], :] / 255
    profile5 = np.array(imcirc5, dtype=np.uint8)[:, xdet[4]] / 255
    profile6 = np.array(imcirc6, dtype=np.uint8)[:, xdet[5]] / 255
    profile7 = np.array(imcirc7, dtype=np.uint8)[ydet[6], :] / 255
    profile8 = np.array(imcirc8, dtype=np.uint8)[ydet[7], :] / 255

    profiles.append(profile1)
    profiles.append(profile2)
    profiles.append(profile3)
    profiles.append(profile4)
    profiles.append(profile5)
    profiles.append(profile6)
    profiles.append(profile7)
    profiles.append(profile8)

    k = 0
    fig = plt.figure(figsize=(8, 12))  # this figure will hold the bibs
    plt.subplots_adjust(hspace=0.35)

    # creating the page to write the results
    dirname = os.path.dirname(filenm)

    # tolerance levels to change at will
    tol = 1.0  # tolearance level
    act = 2.0  # action level
    phantom_distance = 3.0  # distance from the bib to the edge of the phantom

    with PdfPages(
        dirname
        + "/"
        + now.strftime("%d-%m-%Y_%H:%M_")
        + dataset[0x0008, 0x1010].value
        + "_Lightrad_report.pdf"
    ) as pdf:
        Page = plt.figure(figsize=(4, 5))
        Page.text(0.45, 0.9, "Report", size=18)
        kk = 0  # counter for data points
        for profile in profiles:
            _, index = u.find_nearest(profile, 0.5)  # find the 50% amplitude point
            # value_near, index = find_nearest(profile, 0.5) # find the 50% amplitude point

            if (  # pylint: disable = consider-using-in
                k == 0 or k == 1 or k == 4 or k == 5
            ):  # there are the bibs in the horizontal
                offset_value_y = round(
                    abs((ydet[k] - index) * (dy / 10)) - phantom_distance, 2
                )

                txt = str(offset_value_y)
                # print('offset_value_y=', offset_value_y)
                if abs(offset_value_y) <= tol:
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="g",
                    )
                elif abs(offset_value_y) > tol and abs(offset_value_y) <= act:
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="y",
                    )
                else:
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="r",
                    )
                kk = kk + 1

                ax = fig.add_subplot(
                    4, 2, k + 1
                )  # plotting all the figures in a single plot

                ax.imshow(
                    np.array(imcirclist[k], dtype=np.uint8) / 255,
                    extent=list_extent[k],
                    origin="upper",
                )
                ax.scatter(
                    list_extent[k][0] + xdet[k] * dx / 100,
                    list_extent[k][3] + ydet[k] * dy / 100,
                    s=30,
                    marker="P",
                    color="y",
                )
                ax.set_title("Bib=" + str(k + 1))
                ax.axhline(
                    list_extent[k][3] + index * dy / 100, color="r", linestyle="--"
                )
                ax.set_xlabel("x distance [cm]")
                ax.set_ylabel("y distance [cm]")
            else:
                offset_value_x = round(
                    abs((xdet[k] - index) * (dx / 10)) - phantom_distance, 2
                )

                txt = str(offset_value_x)
                if abs(offset_value_x) <= tol:
                    # print('1')
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="g",
                    )
                elif abs(offset_value_x) > tol and abs(offset_value_x) <= act:
                    # print('2')
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="y",
                    )
                else:
                    # print('3')
                    Page.text(
                        0.1,
                        0.8 - kk / 10,
                        "Point" + str(kk + 1) + " offset=" + txt + " mm",
                        color="r",
                    )
                kk = kk + 1

                ax = fig.add_subplot(
                    4, 2, k + 1
                )  # plotting all the figures in a single plot

                ax.imshow(
                    np.array(imcirclist[k], dtype=np.uint8) / 255,
                    extent=list_extent[k],
                    origin="upper",
                )
                ax.scatter(
                    list_extent[k][0] + xdet[k] * dx / 100,
                    list_extent[k][3] + ydet[k] * dy / 100,
                    s=30,
                    marker="P",
                    color="y",
                )
                ax.set_title("Bib=" + str(k + 1))
                ax.axvline(
                    list_extent[k][0] + index * dx / 100, color="r", linestyle="--"
                )
                ax.set_xlabel("x distance [cm]")
                ax.set_ylabel("y distance [cm]")

            k = k + 1

        pdf.savefig()
        pdf.savefig(fig)

        # we now need to select a horizontal and a vertical profile to find the edge of the field from an image
        # for the field size calculation
        im = Image.fromarray(255 * ArrayDicom)

        if ioptn.startswith(("y", "yeah", "yes")):
            PROFILE = {
                "horizontal": 270,
                "vertical": 430,
            }  # location to extract the horizontal and vertical profiles if this is a linac
        else:
            PROFILE = {
                "horizontal": 470,
                "vertical": 510,
            }  # location to extract the horizontal and vertical profiles if this is a true beam

        profilehorz = (
            np.array(im, dtype=np.uint8)[PROFILE["horizontal"], :] / 255
        )  # we need to change these limits on a less specific criteria
        profilevert = np.array(im, dtype=np.uint8)[:, PROFILE["vertical"]] / 255

        # top_edge, index_top = find_nearest(profilevert[0:height//2], 0.5) # finding the edge of the field on the top
        # bot_edge, index_bot = find_nearest(profilevert[height//2:height], 0.5) # finding the edge of the field on the bottom
        _, index_top = u.find_nearest(
            profilevert[0 : height // 2], 0.5
        )  # finding the edge of the field on the top
        _, index_bot = u.find_nearest(
            profilevert[height // 2 : height], 0.5
        )  # finding the edge of the field on the bottom

        # l_edge, index_l = find_nearest(profilehorz[0:width//2], 0.5) #finding the edge of the field on the bottom
        # r_edge, index_r = find_nearest(profilehorz[width//2:width], 0.5) #finding the edge of the field on the right
        _, index_l = u.find_nearest(
            profilehorz[0 : width // 2], 0.5
        )  # finding the edge of the field on the bottom
        _, index_r = u.find_nearest(
            profilehorz[width // 2 : width], 0.5
        )  # finding the edge of the field on the right

        fig2 = plt.figure(
            figsize=(7, 5)
        )  # this figure will show the vertical and horizontal calculated field size
        ax = fig2.subplots()
        ax.imshow(ArrayDicom, extent=extent, origin="upper")
        ax.set_xlabel("x distance [cm]")
        ax.set_ylabel("y distance [cm]")

        # adding a vertical arrow
        ax.annotate(
            s="",
            xy=(PROFILE["vertical"] * dx / 10, index_top * dy / 10),
            xytext=(PROFILE["vertical"] * dx / 10, (height // 2 + index_bot) * dy / 10),
            arrowprops=dict(arrowstyle="<->", color="r"),
        )  # example on how to plot a double headed arrow
        ax.text(
            (PROFILE["vertical"] + 10) * dx / 10,
            (height // 1.25) * dy / 10,
            "Vfs="
            + str(round((height // 2 + index_bot - index_top) * dy / 10, 2))
            + "cm",
            rotation=90,
            fontsize=14,
            color="r",
        )

        # adding a horizontal arrow
        # print(index_l*dx, index_l, PROFILE['horizontal']*dy, PROFILE['horizontal'])
        ax.annotate(
            s="",
            xy=(index_l * dx / 10, PROFILE["horizontal"] * dy / 10),
            xytext=((width // 2 + index_r) * dx / 10, PROFILE["horizontal"] * dy / 10),
            arrowprops=dict(arrowstyle="<->", color="r"),
        )  # example on how to plot a double headed arrow
        ax.text(
            (width // 2) * dx / 10,
            (PROFILE["horizontal"] - 10) * dy / 10,
            "Hfs=" + str(round((width // 2 + index_r - index_l) * dx / 10, 2)) + "cm",
            rotation=0,
            fontsize=14,
            color="r",
        )

        pdf.savefig(fig2)


if __name__ == "__main__":
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

    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str, help="Input the Light/Rad file")
    args = parser.parse_args()

    filename = args.file

    read_dicom(filename, ioption)
