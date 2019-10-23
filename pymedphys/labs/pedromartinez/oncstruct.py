"""
Script name: oncstruct

Description: Tool for processing of Oncentra structure files

Author: Pedro Martinez
pedro.enrique.83@gmail.com
5877000722
Date:2019-05-10

"""


import os
import sys
sys.path.append('C:\Program Files\GDCM 2.8\lib')
import pydicom
import numpy as np
import re
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import matplotlib.colors as colors
from mayavi import mlab



# def process_file(filename,ax):
def process_file(filename):
    dataset = pydicom.dcmread(filename)
    # print(dataset)
    # exit(0)
    # ax.set_xlabel('x distance [mm]')
    # ax.set_ylabel('y distance [mm]')
    # ax.set_zlabel('z distance [mm]')

    roi_num=[]
    roi_color=[]

    xs_tot = []
    ys_tot = []
    zs_tot = []
    element = []
    desc_item=[]
    color=[]
    layer = []


    for item in dataset[0x3006,0x0080]:
        desc_item.append((int(item[0x3006,0x0084].value),item[0x3006,0x0088].value,item[0x3006,0x00a4].value))

    desc_item=np.asarray(desc_item)


    k=0
    for elem in dataset[0x3006,0x0039]: #CTV, lesion, etc
        xs_el = []
        ys_el = []
        zs_el = []
        roi_color=np.asarray(elem[0x3006, 0x002a].value)
        # print(roi_color/255,np.shape(roi_color))
        # exit(0)
        hex_color=colors.rgb2hex(np.asarray(roi_color)/255)
        roi_num.append(elem[0x3006, 0x0084].value)
        kk = 0
        try:
            for contour in elem[0x3006,0x0040]:
                # xs = []
                # ys = []
                # zs = []
                for i in range(0,contour[0x3006,0x0050].VM,3):
                    # xs.append(contour[0x3006,0x0050][i])
                    # ys.append(contour[0x3006, 0x0050][i+1])
                    # zs.append(contour[0x3006, 0x0050][i+2])
                    xs_tot.append(contour[0x3006,0x0050][i])
                    ys_tot.append(contour[0x3006, 0x0050][i+1])
                    zs_tot.append(contour[0x3006, 0x0050][i+2])
                    xs_el.append(contour[0x3006,0x0050][i])
                    ys_el.append(contour[0x3006, 0x0050][i+1])
                    zs_el.append(contour[0x3006, 0x0050][i+2])
                    color.append(roi_color)
                    element.append(desc_item[k,:])
                    layer.append(kk)
                    # print('kk=',kk)
                kk = kk + 1

                #for matplotlib3d
                # verts = [list(zip(x, y, z))]
                # print(verts,np.shape(verts))
                # exit(0)

                # poly=Poly3DCollection(verts,alpha=0.01)
                # poly.set_color(hex_color)
                # poly.set_edgecolor('k')
                # ax.add_collection3d(poly)


            #for mayavi (temporary until I figure how to make closed surfaces)
            col = (roi_color[0]/255, roi_color[1]/255, roi_color[2]/255)
            mlab.plot3d(xs_el, ys_el, zs_el,tube_radius=0.1,color=col)


        except:
            print('no contour data')

        k=k+1

    elem_data=np.transpose(np.vstack((np.transpose(element),np.transpose(np.asarray(color)),layer,xs_tot,ys_tot,zs_tot)))

    return elem_data # returning a matrix with all the data containing (element number, element description(CTV1,Urethra,etc.), element type (PTV,etc.),color, contour/layer and point location (x,y,z))

    # xtot = np.array(xs_tot).astype(np.float)
    # ytot = np.array(ys_tot).astype(np.float)
    # ztot = np.array(zs_tot).astype(np.float)
    #
    # mlab.plot3d(xtot, ytot, ztot)

    # ax.set_xlim3d(np.min(xs_tot), np.max(xs_tot))
    # ax.set_ylim3d(np.min(ys_tot), np.max(ys_tot))
    # ax.set_zlim3d(np.min(zs_tot), np.max(zs_tot))
    # print(roi_color)


