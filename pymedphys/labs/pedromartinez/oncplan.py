"""
Script name: oncplan

Description: Tool for processing of Oncentra plan files

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
from mayavi import mlab




# def process_file(filename,ax):
def process_file(filename):
    dataset = pydicom.dcmread(filename)
    source_dataset=[]
    xs=[]
    ys=[]
    zs=[]
    ts=[]


    for elem in dataset[0x300a, 0x0230][0][0x300a, 0x0280]:
        for pos in elem[0x300a, 0x02d0]:
            x,y,z=pos[0x300a, 0x02d4].value
            source_dataset.append([ elem[0x300a, 0x0282].value, elem[0x300a, 0x0284].value, elem[0x300a, 0x0286].value, pos[0x300a, 0x0112].value, x , y, z, pos[0x300a, 0x02d6].value])

    source_dataset = np.asarray(source_dataset)
    print(source_dataset.shape)
    for i in range(1,source_dataset.shape[0],2):
        x=source_dataset[i,4]
        y=source_dataset[i,5]
        z=source_dataset[i,6]
        tw=source_dataset[i,7]-source_dataset[i-1,7]
        xs.append(x)
        ys.append(y)
        zs.append(z)
        ts.append(tw/100*source_dataset[i,2])
        # print('tw=',tw,source_dataset[i,7],source_dataset[i-1,7])

    #for matplotlib3d
    # ax.scatter(xs, ys, zs, s=ts)

    #for mayavi
    return xs, ys, zs, ts # returning the positions of the sources and the dwell time







