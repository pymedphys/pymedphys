"""
Script name: oncdose

Description: Tool for processing of Oncentra dose files

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
from mayavi import mlab

# # axial visualization and scrolling
# def multi_slice_viewer(volume, origin, dx, dy, dz,ax,fig):
#     xv, yv = np.mgrid[origin[0]:origin[0] + (volume.shape[2] * dx):dx,
#               origin[1]:origin[1] + (volume.shape[1] * dy):dy]
#     # remove_keymap_conflicts({'j', 'k'})
#     # fig, ax = plt.subplots()
#     ax.volume = volume
#     ax.index = volume.shape[0] // 2
#     # print(ax.index)
#     # print(origin,volume.shape)
#     # extent = (origin[0], origin[0] + (volume.shape[2] * dx),
#     #           origin[1]+ (volume.shape[1] * dy), origin[1])
#     # ax.imshow(volume[ax.index, :, :], extent=extent, origin='upper')
#     # ax.imshow(volume[ax.index, :, :])
#     poly=ax.contourf(xv, yv, np.transpose(volume[ax.index, :, :]), offset=(origin[2]-ax.index*dz))
#     # ax.set_xlabel('x distance [mm]')
#     # ax.set_ylabel('y distance [mm]')
#     # ax.set_title("slice=" + str(ax.index)+ " , z="+ str(origin[2]-ax.index*dz)+' mm')
#     # fig.suptitle('Axial view', fontsize=16)
#     args=[origin,dx,dy,dz]
#     fig.canvas.mpl_connect('key_press_event', lambda event: process_key_axial(event, origin, dx, dy, dz,poly,volume))
#
#
#
# def process_key_axial(event, origin, dx, dy, dz,poly,volume):
#     fig = event.canvas.figure
#     ax = fig.axes[0]
#     if event.key == 'b':
#         previous_slice_axial(ax,origin, dx, dy, dz,poly,volume)
#     elif event.key == 'n':
#         next_slice_axial(ax,origin, dx, dy, dz,poly,volume)
#     ax.set_title("slice=" + str(ax.index)+ " , z="+ str(origin[2]-ax.index*dz)+' mm')
#     fig.canvas.draw()
#
#
# def previous_slice_axial(ax,origin, dx, dy, dz,poly,volume):
#     xv, yv = np.mgrid[origin[0]:origin[0] + (volume.shape[2] * dx):dx,
#               origin[1]:origin[1] + (volume.shape[1] * dy):dy]
#     volume = ax.volume
#     ax.index = (ax.index - 1) % volume.shape[0]  # wrap around using %
#     print(ax.index, (origin[2] - ax.index * dz))
#     # ax.images[0].set_array(volume[ax.index, :, :])
#     poly.set_array(volume[ax.index, :, :])
#     ax.redraw_in_frame()
#
#
#
#
# def next_slice_axial(ax,origin, dx, dy, dz,poly,volume):
#     xv, yv = np.mgrid[origin[0]:origin[0] + (volume.shape[2] * dx):dx,
#               origin[1]:origin[1] + (volume.shape[1] * dy):dy]
#     volume = ax.volume
#     ax.index = (ax.index + 1) % volume.shape[0]
#     print(ax.index, (origin[2] - ax.index * dz))
#     # ax.images[0].set_array(volume[ax.index, :, :])
#     # poly.set_array(volume[ax.index, :, :])
#     poly = ax.contourf(xv, yv, np.transpose(volume[ax.index, :, :]), offset=(origin[2] - ax.index * dz))












# def process_file(filename,ax,fig):
def process_file(filename):
    """This function process an Oncentra dose file  """
    # print('Starting dose calculation')
    dataset = pydicom.dcmread(filename)
    # print(dataset)
    ArrayDicom = np.zeros((dataset.Rows, dataset.Columns, 0), dtype=dataset.pixel_array.dtype)
    ArrayDicom = dataset.pixel_array
    # print(np.shape(ArrayDicom))
    # exit(0)
    # plt.figure()

    # plt.show()



    # print("slice thickness [mm]=", dataset.SliceThickness)
    # SID = dataset.RTImageSID
    # dx = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[0]) / 1000)
    # dy = 1 / (SID * (1 / dataset.ImagePlanePixelSpacing[1]) / 1000)
    dz = dataset.SliceThickness
    dy,dx = dataset.PixelSpacing
    origin = dataset[0x0020, 0x0032].value
    print("pixel spacing depth [mm]=", dz)
    print("pixel spacing row [mm]=", dy)
    print("pixel spacing col [mm]=", dx)
    print('origin=',origin)
    # print(dataset)
    # print('comment',dataset.DoseComment)


    #for matplotlib3d
    # x= np.linspace(origin[0],origin[0] + (ArrayDicom.shape[2] * dx),ArrayDicom.shape[2])
    # y= np.linspace(origin[1],origin[1] + (ArrayDicom.shape[1] * dy),ArrayDicom.shape[1])
    # z= np.linspace(origin[2],origin[2] - (ArrayDicom.shape[0] * dz),ArrayDicom.shape[0])
    # print(np.shape(xv),np.shape(yv),np.shape(ArrayDicom[5,:,:]))

    # multi_slice_viewer(ArrayDicom, origin, dx, dy, dz,ax,fig)
    # plt.show()




    #for mayavi
    x, y, z = np.mgrid[origin[0]:origin[0] + (ArrayDicom.shape[2] * dx):dx,
              origin[1]:origin[1] + (ArrayDicom.shape[1] * dy):dy,
              origin[2] - (ArrayDicom.shape[0] * dz):origin[2]:dz]




    volume=np.flip(np.swapaxes(ArrayDicom,axis1=0,axis2=2),axis=2) #need to swap two axis and flip z since the axis must be increasing


    return x, y, z, dx, dy, dz, volume










