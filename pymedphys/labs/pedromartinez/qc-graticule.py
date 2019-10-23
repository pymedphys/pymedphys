#############################START LICENSE##########################################
# Copyright (C) 2019 Pedro Martinez
#
# # This program is free software: you can redistribute it and/or modify
# # it under the terms of the GNU Affero General Public License as published
# # by the Free Software Foundation, either version 3 of the License, or
# # (at your option) any later version (the "AGPL-3.0+").
#
# # This program is distributed in the hope that it will be useful,
# # but WITHOUT ANY WARRANTY; without even the implied warranty of
# # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# # GNU Affero General Public License and the additional terms for more
# # details.
#
# # You should have received a copy of the GNU Affero General Public License
# # along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# # ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# # Affero General Public License. These additional terms are Sections 1, 5,
# # 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# # where all references to the definition "License" are instead defined to
# # mean the AGPL-3.0+.
#
# # You should have received a copy of the Apache-2.0 along with this
# # program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.
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

import os
import sys

# sys.path.append('C:\Program Files\GDCM 2.8\lib')
import pydicom
import subprocess
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm
import numpy as np
import argparse
import cv2
from skimage.feature import blob_log
from math import *
from operator import itemgetter
import utils as u
from PIL import Image


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


# axial visualization and scrolling
def viewer(volume, dx, dy,center,title,textstr):
    # remove_keymap_conflicts({'j', 'k'})
    fig = plt.figure(figsize=(12,7))
    ax = fig.subplots()
    ax.volume = volume
    width=volume.shape[1]
    height=volume.shape[0]
    extent = (0, 0 + (volume.shape[1] * dx),
              0, 0 + (volume.shape[0] * dy))
    img=ax.imshow(volume, extent=extent)
    # img=ax.imshow(volume)
    ax.set_xlabel('x distance [mm]')
    ax.set_ylabel('y distance [mm]')
    # ax.set_xlabel('x pixel')
    # ax.set_ylabel('y pixel')
    ax.set_xlim(width*dx/2-10, width*dx/2+10)
    ax.set_ylim(height*dy/2-10, height*dy/2+10)

    # fig.suptitle('Image', fontsize=16)
    print(title[0])
    ax.set_title(title[0]+'\n'+title[1], fontsize=16)

    # for i in range(0,len(poly)): #maybe at a later stage we will add polygons drawings
    #     ax.add_patch(poly[i])
    ax.text((volume.shape[1]+250)*dx,(volume.shape[0])*dy,textstr)
    fig.subplots_adjust(right=0.75)
    fig.colorbar(img, ax=ax, orientation='vertical')
    # fig.canvas.mpl_connect('key_press_event', process_key_axial)
    for x,y in center:
        # ax.scatter(x,y)
        # ax.scatter(x*dx+dx/2,(volume.shape[0]-y)*dy-dy/2) #adding dx/2 and subtracting dy/2 correctly puts the point in the center of the pixel when using extents and not in the edge.
        ax.scatter(x*dx,(volume.shape[0]-y)*dy,label=title,color='k'

                   ) #perfect!

    return fig, ax







def shape_detect(c):
    shape='unidentified'
    peri=cv2.arcLength(c,True)
    approx=cv2.approxPolyDP(c) #number of vertices in the contour
    if len(approx)==3:
        shape='triangle'
    elif len(approx)==4:
        #compute the bounding box of the contour and find the aspect ratio
        (x,y,w,h)=cv2.boundingRect(approx)
        ar=w/float(h)

        shape='square' if ar >=0.95 and ar <=1.05 else 'rectangle'
    else:
        shape='circle'

    return shape



def scalingAnalysis(ArrayDicom_o,dx,dy,title):  #determine scaling
    ArrayDicom = u.norm01(ArrayDicom_o)
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]

    blobs_log = blob_log(ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20,
                         threshold=0.15)  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    center = []
    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(point_det, key=itemgetter(2),
                       reverse=True)  # here we sort by the radius of the dot bigger dots are around the center and edges


    print(point_det[:6])  # print the first six points, all the points and only the first component
    print(np.asarray(point_det)[:6,0])  # print the first six points, all the points and only the first component
    point_det=np.asarray(point_det)

    #now we need to select the most extreme left and right point
    print(np.shape(ArrayDicom)[0]//2)
    print(abs(point_det[:6,1]-np.shape(ArrayDicom)[0]//2)<10)
    point_sel=[]
    for i in range(0,6):
        if abs(point_det[i, 1] - np.shape(ArrayDicom)[0] // 2) < 10:
            point_sel.append(abs(point_det[i, :]))

    point_sel=np.asarray(point_sel)
    imax = np.argmax(point_sel[:,0])
    imin = np.argmin(point_sel[:,0])

    print(point_sel[imax,:],point_sel[imin,:])
    distance = np.sqrt((point_sel[imax,0]-point_sel[imin,0])*(point_sel[imax,0]-point_sel[imin,0])*dx*dx + (point_sel[imax,1]-point_sel[imin,1])*(point_sel[imax,1]-point_sel[imin,1])*dy*dy)/10.
    print('distance=',distance,'cm') #distance is reported in cm


    return distance



def full_imageProcess(ArrayDicom_o,dx,dy,title):  #process a full image
    ArrayDicom = u.norm01(ArrayDicom_o)
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]

    blobs_log = blob_log(ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20,
                         threshold=0.15)  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    center = []
    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(point_det, key=itemgetter(2), reverse=True)  # here we sort by the radius of the dot bigger dots are around the center and edges

    # we need to find the centre dot as well as the larger dots on the sides of the image

    # for j in range(0, len(point_det)):
    #     x, y, r = point_det[j]
    #     center.append((int(round(x)), int(round(y))))

    array_center = np.array(point_det, dtype=float)  # array with the centre of the points detected

    # now that we have detected the centre we are going to increase the precision of the detected point
    im_centre = Image.fromarray(
        255 * ArrayDicom[height // 2 - 20:height // 2 + 20, width // 2 - 20:width // 2 + 20])
    im_centre = im_centre.resize((im_centre.width * 10, im_centre.height * 10), Image.LANCZOS)

    xdet_int, ydet_int = point_detect_singleImage(im_centre)
    xdet = int(width // 2 - 20) + xdet_int / 10
    ydet = int(height // 2 - 20) + ydet_int / 10

    center.append((xdet, ydet))

    textstr = ''

    print('center=',center)
    fig, ax=viewer(u.range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return fig, ax, center




def full_imageProcess_noGraph(ArrayDicom_o,dx,dy,title):  #process a full image
    ArrayDicom = u.norm01(ArrayDicom_o)
    height = np.shape(ArrayDicom)[0]
    width = np.shape(ArrayDicom)[1]

    blobs_log = blob_log(ArrayDicom, min_sigma=1, max_sigma=5, num_sigma=20,
                         threshold=0.15)  # run on windows, for some stupid reason exclude_border is not recognized in my distro at home

    center = []
    point_det = []
    for blob in blobs_log:
        y, x, r = blob
        point_det.append((x, y, r))

    point_det = sorted(point_det, key=itemgetter(2), reverse=True)  # here we sort by the radius of the dot bigger dots are around the center and edges

    # we need to find the centre dot as well as the larger dots on the sides of the image

    # for j in range(0, len(point_det)):
    #     x, y, r = point_det[j]
    #     center.append((int(round(x)), int(round(y))))

    array_center = np.array(point_det, dtype=float)  # array with the centre of the points detected

    # now that we have detected the centre we are going to increase the precision of the detected point
    im_centre = Image.fromarray(
        255 * ArrayDicom[height // 2 - 20:height // 2 + 20, width // 2 - 20:width // 2 + 20])
    im_centre = im_centre.resize((im_centre.width * 10, im_centre.height * 10), Image.LANCZOS)

    xdet_int, ydet_int = point_detect_singleImage(im_centre)
    xdet = int(width // 2 - 20) + xdet_int / 10
    ydet = int(height // 2 - 20) + ydet_int / 10

    center.append((xdet, ydet))

    textstr = ''

    # fig, ax=viewer(u.range_invert(ArrayDicom_o), dx, dy, center, title, textstr)

    return center











def point_detect_singleImage(imcirclist):
    detCenterXRegion = []
    detCenterYRegion = []

    print('Finding bibs in phantom...')
    grey_img = np.array(imcirclist, dtype=np.uint8)  # converting the image to grayscale
    blobs_log = blob_log(grey_img, min_sigma=15, max_sigma=50, num_sigma=10, threshold=0.05)
    # print(blobs_log)
    # exit(0)

    centerXRegion = []
    centerYRegion = []
    centerRRegion = []
    grey_ampRegion = []
    for blob in blobs_log:
        y, x, r = blob
        center = (int(x), int(y))
        centerXRegion.append(x)
        centerYRegion.append(y)
        centerRRegion.append(r)
        grey_ampRegion.append(grey_img[int(y), int(x)])
        radius = int(r)
        # print('center=', center, 'radius=', radius, 'value=', img[center], grey_img[center])

    xindx = int(centerXRegion[np.argmin(grey_ampRegion)])
    yindx = int(centerYRegion[np.argmin(grey_ampRegion)])
    rindx = int(centerRRegion[np.argmin(grey_ampRegion)])

    detCenterXRegion=xindx
    detCenterYRegion=yindx

    return detCenterXRegion,detCenterYRegion














# def read_dicom(filename1,filename2,ioption):
def read_dicom(dirname,ioption):
    for subdir, dirs, files in os.walk(dirname):
        list_title = []
        list_ArrayDicom=[]
        list_gantry_angle=[]
        list_collimator_angle=[]
        list_figs=[]
        center_g0c90=[(0,0)]
        center_g0=[(0,0)]
        dx=0
        dy=0

        k=0 # we callect all the images in ArrayDicom
        for file in tqdm(sorted(files)):
            print(file)

            if os.path.splitext(dirname + file)[1] == '.dcm':
                dataset = pydicom.dcmread(dirname + file)
                station_name=dataset[0x3002,0x0020].value
                gantry_angle=dataset[0x300a,0x011e].value
                collimator_angle=dataset[0x300a,0x0120].value

                list_gantry_angle.append(gantry_angle)
                list_collimator_angle.append(collimator_angle)

                # title = ('Gantry= ' + str(gantry_angle), 'Collimator= ' + str(collimator_angle))
                title = ('g' + str(gantry_angle),'c' + str(collimator_angle))
                print(title)

                if k==0:
                    # title = ('Gantry= ' + str(gantry_angle), 'Collimator= ' + str(collimator_angle))
                    title = ('g' + str(gantry_angle),'c' + str(collimator_angle))
                    list_title.append(title)
                    ArrayDicom = dataset.pixel_array
                    height = np.shape(ArrayDicom)[0]
                    width = np.shape(ArrayDicom)[1]
                    SID = dataset.RTImageSID
                    dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
                    dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
                    print("pixel spacing row [mm]=", dx)
                    print("pixel spacing col [mm]=", dy)

                else:
                    list_title.append(title)
                    tmp_array = dataset.pixel_array
                    tmp_array = u.norm01(tmp_array)
                    ArrayDicom = np.dstack((ArrayDicom, tmp_array))

            k=k+1


    # After we colect all the images we only select g0c90 and g0c270 to calculate the center at g0
    for i in range(0,len(list_title)):
        if list_title[i][0]=='g0' and list_title[i][1]=='c90':
            height = np.shape(ArrayDicom[:, :, i])[0]
            width = np.shape(ArrayDicom[:, :, i])[1]
            fig_g0c90, ax_g0c90, center_g0c90 = full_imageProcess(ArrayDicom[:, :, i], dx, dy, list_title[i])
            center_g0[0]= (center_g0[0][0] + center_g0c90[0][0]*.5,center_g0[0][1] + center_g0c90[0][1]*.5)

            list_figs.append(fig_g0c90)  # we plot always the image at g0c90

        if list_title[i][0]=='g0' and list_title[i][1]=='c270':
            center_g0c270 = full_imageProcess_noGraph(ArrayDicom[:, :, i], dx, dy, list_title[i])
            center_g0[0]= (center_g0[0][0] + center_g0c270[0][0]*.5,center_g0[0][1] + center_g0c270[0][1]*.5)





    for i in range(0,len(list_title)):
        if list_title[i][1] != 'c90':
            center=full_imageProcess_noGraph(ArrayDicom[:,:,i], dx, dy, list_title[i])

            x_g0,y_g0 = center_g0[0]
            x,y = center[0]

            dist = sqrt((x_g0 - x) * (x_g0 - x) * dx * dx + (y_g0 - y) * (y_g0 - y) * dy * dy)
            # dist = sqrt((width//2 - x) * (width//2 - x) * dx * dx + (height//2 - y) * (height//2 - y) * dy * dy)

            textstr = 'offset' + str(list_title[i]) + '=' + str(round(dist, 4)) + ' mm'

            ax_g0c90.scatter(x * dx, (ArrayDicom[:,:,i].shape[0] - y) * dy, label=textstr)  # perfect!

            print(list_title[i],'center_g0c90=',center_g0c90,'center=',center,dist)
            ax_g0c90.legend(bbox_to_anchor=(1.25, 1), loc=2, borderaxespad=0.)


    with PdfPages(dirname + '/' + 'Graticule_report.pdf') as pdf:
        pdf.savefig(fig_g0c90)

    exit(0)




    # # Normal mode:
    # print()
    # print("Filename.........:", file)
    # print("Storage type.....:", dataset.SOPClassUID)
    # print()
    #
    # pat_name = dataset.PatientName
    # display_name = pat_name.family_name + ", " + pat_name.given_name
    # print("Patient's name...:", display_name)
    # print("Patient id.......:", dataset.PatientID)
    # print("Modality.........:", dataset.Modality)
    # print("Study Date.......:", dataset.StudyDate)
    # print("Gantry angle......", dataset.GantryAngle)
    # #
    # # if 'PixelData' in dataset:
    # #     rows = int(dataset.Rows)
    # #     cols = int(dataset.Columns)
    # #     print("Image size.......: {rows:d} x {cols:d}, {size:d} bytes".format(
    # #         rows=rows, cols=cols, size=len(dataset.PixelData)))
    # #     if 'PixelSpacing' in dataset:
    # #         print("Pixel spacing....:", dataset.PixelSpacing)
    # #
    # # # use .get() if not sure the item exists, and want a default value if missing
    # # print("Slice location...:", dataset.get('SliceLocation', "(missing)"))
    plt.show()



parser = argparse.ArgumentParser()
parser.add_argument('direpid',type=str,help="Input the directory name")

# parser.add_argument('epid1',type=str,help="Input the filename")
# parser.add_argument('epid2',type=str,help="Input the filename")
# parser.add_argument('-a', '--add', nargs='?', type=argparse.FileType('r'), help='additional file for averaging before processing')
args=parser.parse_args()

dirname=args.direpid

# filename1=args.epid1
# filename2=args.epid2





while True:  # example of infinite loops using try and except to catch only numbers
    line = input('Are these files from a clinac [yes(y)/no(n)]> ')
    try:
        ##        if line == 'done':
        ##            break
        ioption = str(line.lower())
        if ioption.startswith(('y', 'yeah', 'yes', 'n', 'no', 'nope')):
            break

    except:
        print('Please enter a valid option:')




# read_dicom(filename1,filename2,ioption)
read_dicom(dirname,ioption)
