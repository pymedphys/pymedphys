"""
 Script name: Oncentra_Visualizer.py

 Description: Integrated toolfor visualization of Oncentra structire, plan and dose files

 Example usage: python Oncentra_Visualizer structure plan dose

 Author: Pedro Martinez
 pedro.enrique.83@gmail.com
 5877000722
 Date:2019-07-18

"""



import os
import sys
import pydicom
import numpy as np
import re
import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import matplotlib.colors as colors
import scipy as sp
import oncstruct
import oncplan
import oncdose
from mayavi import mlab
import argparse
import wx


#matplotlib.use('WxAgg')
#matplotlib.use('Qt5Agg')




#try:
#    structname = str(sys.argv[1])
    #print(structname)
#except:
#    print('Please enter a valid filename')
    #print("Use the following command to run this script")
    #print("python Oncentra_Visualizer.py \"[structures dicom]\" \"[plan dicom]\" \"[dose dicom]\"")

#try:
#    planname = str(sys.argv[2])
    #print(planname)
#except:
#    print('Please enter a valid filename')
    #print("Use the following command to run this script")
    #print("python Oncentra_Visualizer.py \"[structures dicom]\" \"[plan dicom]\" \"[dose dicom]\"")


#try:
#    dosename = str(sys.argv[3])
    #print(dosename)
#except:
#    print('Please enter a valid filename')
    #print("Use the following command to run this script")
    #print("python Oncentra_Visualizer.py \"[structures dicom]\" \"[plan dicom]\" \"[dose dicom]\"")


parser = argparse.ArgumentParser()
#parser.add_argument('structure',type=str,help="Input the structure file")
parser.add_argument('-s', '--structure', nargs='?', type=argparse.FileType('r'), help='structure file, in DICOM format')
parser.add_argument('-p', '--plan', nargs='?', type=argparse.FileType('r'), help='plan file, in DICOM format')
parser.add_argument('-d', '--dose', nargs='?', type=argparse.FileType('r'), help='dose file, in DICOM format')
args=parser.parse_args()

#structname=args.structure


mlab.figure(bgcolor=(1,1,1), fgcolor=(0.,0.,0.))
scene = mlab.gcf().scene
scene.renderer.use_depth_peeling=1

#using matplotlib3d
# oncdose.process_file(dosename,ax,fig)
# oncstruct.process_file(structname,ax)
# oncplan.process_file(planname,ax)


#elem_data=oncstruct.process_file(structname)

if args.structure:
    structname=args.structure
    print(structname.name)
    elem_data=oncstruct.process_file(structname.name)


if args.dose:
    dosename=args.dose
    print(dosename.name)
    #using mayavi
    x,y,z,dx,dy,dz,volume=oncdose.process_file(dosename.name)
    mlab.volume_slice(x, y, z, volume, plane_orientation='z_axes')
    # mlab.contour3d(x,y,z,volume,contours=15,opacity=1)
    mlab.colorbar(title='Dose [cGy]', orientation='vertical', )



if args.plan:
    planname=args.plan
    print(planname.name)
    xs, ys, zs, ts=oncplan.process_file(planname.name)
    mlab.points3d(xs, ys, zs, ts)



ax=mlab.axes(nb_labels=8)
ax.axes.font_factor=1

mlab.show()
