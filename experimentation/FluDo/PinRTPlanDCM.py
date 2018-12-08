# Copyright (C) 2018 Ben Cooper

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
# Affrero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import os
import numpy as np
import dicom as dcm
import matplotlib.pyplot as plt
from scipy import interpolate as interpl
#make an empty Opening Density ndarray for 60 MLC leaves
# ie a Varian Millennium 120

class PinRTPlanDCM:
    '''A class to hold RTPLAN DCM objects from Pinnacle
    and reconstruct Opening Densities for beams.  Use the scipy
    package interpolate.RectBivariateSpline to solve the problem
    of variable MLC leaf widths (5mm and 10mm) - see get_interp_single

    INPUT:
    my_dcm      : full path to input RTPLAN dcm file

    ATTRIBS:
    ds          : "dicom structure" object holding parsed RTPLAN data
    ods[]       : list of MLC original opening densities, one per beam
    flus[]      : as above but interpolated for MLC spatial width variation
    gant_angles[]:gantry angles from RTPLAN dcm object '''


    def __init__(self, my_dcm= ''):
        self.pin_dcm_file = None

        if my_dcm != '':
            if os.path.exists(my_dcm):
                self.pin_dcm_file = my_dcm
        else:
            print("Cannot see any RTPLAN dicom file ...")
            return

        print(self.pin_dcm_file,'xxxxxxxxxxxxxxxxx')

        #self.od = np.zeros((60,400))
        self.ds = dcm.read_file(self.pin_dcm_file)
        self.num_beams = len(self.ds.BeamSequence)
        self.ods = [None] * self.num_beams
        self.flus = [None] * self.num_beams
        self.gant_angles = [None] * self.num_beams
        self.beam_desc = [None] * self.num_beams
        self.x1jaw = [None] * self.num_beams
        self.x2jaw = [None] * self.num_beams
        self.y1jaw = [None] * self.num_beams
        self.y2jaw = [None] * self.num_beams
        self.get_ODM()
        print(self.num_beams,'no. of beams')

    def show_maps(self, src, title):
        fig1, ax1 = plt.subplots()
        ax1.set_title(title)
        im1 = ax1.imshow(src)
        plt.show(block=True)

    def get_interp_single(self, flu):
        my_flu = flu
        flu_y = [-19.5, -18.5, -17.5, -16.5, -15.5, -14.5, -13.5, -12.5, -11.5, -10.5, -9.75,
         -9.25, -8.75, -8.25, -7.75, -7.25, -6.75, -6.25, -5.75, -5.25, -4.75, -4.25,
         -3.75, -3.25, -2.75, -2.25, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25,
         1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75, 5.25, 5.75, 6.25, 6.75, 7.25, 7.75,
         8.25, 8.75, 9.25, 9.75, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5,
         19.5]

        flu_x = np.linspace(-19.95, 19.95, 400)
        flu_yy = np.linspace(-19.95, 19.95, 400)

        #first create interpolating object tmp
        tmp = interpl.RectBivariateSpline(flu_y, flu_x, my_flu,kx=1, ky=1,s=0)

        tmp2 = tmp(flu_yy, flu_x)
        return tmp2

    def get_ODM(self):
        for bm in range(self.num_beams):
            self.gant_angles[bm] = float(self.ds.BeamSequence[bm].ControlPointSequence[0].GantryAngle)
            #self.beam_desc[bm] = str(self.ds.BeamSequence[bm].BeamDescription)
            self.ods[bm] = np.zeros((60,400))
            num_cps = len(self.ds.BeamSequence[bm].ControlPointSequence)
            print (num_cps)
            cpw = list()
            for cp in range(num_cps):
                # get all the cumlative control point weights into cpw list
                cpw.append(self.ds.BeamSequence[bm].ControlPointSequence[cp].CumulativeMetersetWeight)

            # get a copy of the jaw positions for each beam from Pinnacle:
            self.x1jaw[bm] =\
                self.ds.BeamSequence[bm].ControlPointSequence[0].BeamLimitingDevicePositionSequence[0].LeafJawPositions[0]

            self.x2jaw[bm] =\
                self.ds.BeamSequence[bm].ControlPointSequence[0].BeamLimitingDevicePositionSequence[0].LeafJawPositions[1]

            self.y1jaw[bm] =\
                self.ds.BeamSequence[bm].ControlPointSequence[0].BeamLimitingDevicePositionSequence[1].LeafJawPositions[0]

            self.y2jaw[bm] =\
                self.ds.BeamSequence[bm].ControlPointSequence[0].BeamLimitingDevicePositionSequence[1].LeafJawPositions[1]
            # NB only look at the "off" control point after a segment has been delivered in Step-and-Shoot,
            # so store "off" CP 1,3,5, ... and ignore "on" CP 0, 2, 4, ...
            for cp in range(1,num_cps, 2):
                #print(cp,"CP")

                #cum_ms_weight = self.ds.BeamSequence[bm].ControlPointSequence[cp].CumulativeMetersetWeight
                dif_weight = cpw[cp] - cpw[cp-1]
                #print(dif_weight)

                #loop over n=60 MLC leaf pairs, lhs bank leaf pos is in first 60, rhs bank is 2nd 60 of
                # .LeafJawPosition[] list.  My vars lhsi and rhsi yield the indicies for the leaves
                # making the boundary of a segment
                for i in range(60):
                    lhsi = round(self.ds.BeamSequence[bm].ControlPointSequence[cp].BeamLimitingDevicePositionSequence[0].LeafJawPositions[i]+200)
                    rhsi = round(self.ds.BeamSequence[bm].ControlPointSequence[cp].BeamLimitingDevicePositionSequence[0].LeafJawPositions[i+60]+199)
                    j = lhsi
                    while True:
                        if (j < rhsi):
                            (self.ods[bm])[i,j] += dif_weight
                            j+=1
                        elif (j==rhsi):
                            (self.ods[bm])[i,j] += dif_weight
                            break

            my_flu = self.get_interp_single(self.ods[bm])
            self.flus[bm] =  my_flu
            #if bm==0:
                #plt.imshow(self.flus[bm])
                #plt.show()



