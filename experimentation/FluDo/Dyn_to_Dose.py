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


from scipy import interpolate as interpl
from scipy import ndimage as ndi
from scipy import stats as spstats
import numpy as np
import os
from pylinac import log_analyzer as lga

class Dyn_to_Dose:
    def __init__(self,my_dir):
        """class to import a folder full of dynalog files for a treatment"""
        #self.my_logs = lga.MachineLogs();
        self.flip_fluences = list()
        self.fluences = list()
        self.gant_angle = list()
        self.interp_fluences = list()
        self.res_mm = 1.0
        self.num_logs = None
        #self.pin_dose_index = list()

        #TODO more rigorous checking of my_dir
        if os.path.exists(my_dir):
            #self.my_logs.from_folder_UI()
            my_logs_tmp = lga.MachineLogs(my_dir)
            self.my_logs= sorted(my_logs_tmp, key=lambda x: x.filename)
        else:
            self.my_logs = None

        self.num_logs = len(self.my_logs)
        self.interp_fluences = [None] * self.num_logs
        self.od_map_index = [None] * self.num_logs

    def do_calcs(self, res_mm=1.0):
        if len(self.my_logs) == 0:
            print("No valid log files loaded ...")
            return
        if (0.5 <= res_mm <= 5.0):
            self.res_mm = res_mm

        self.gant_angle = list()
        self.fluences = list()

        count=0
        for log in self.my_logs:
            self.fluences.append(log.fluence.actual.calc_map(resolution=res_mm))
            #print("beam delivered at gantry angle (Varian units): ", log.axis_data.gantry.actual[0])
            #print("Normal gantry angle: ",(540.0 - log.axis_data.gantry.actual[0])%360.0)
            self.gant_angle.append((540.0 - log.axis_data.gantry.actual[0])%360.0)
            count +=1

    def do_flip(self):
        self.flip_fluences = list()
        for log in self.my_logs:
            tmp = log.fluence.actual.calc_map(resolution=1.0)
            self.flip_fluences.append(np.flipud(tmp))

        for x in range (self.num_logs):
            if self.gant_angle[x] <= 90 or self.gant_angle[x] >= 270:
                print ('Gant is {0:3.1f} and I would LR flip'.format(self.gant_angle[x]))

                #self.flip_fluences[x] = np.fliplr(self.flip_fluences[x])


    def make_interp_single(self, index, y_dim, x_dim):
        assert index <= self.num_logs, "index out of bounds"

        flu_y = [-19.5, -18.5, -17.5, -16.5, -15.5, -14.5, -13.5, -12.5, -11.5, -10.5, -9.75,
         -9.25, -8.75, -8.25, -7.75, -7.25, -6.75, -6.25, -5.75, -5.25, -4.75, -4.25,
         -3.75, -3.25, -2.75, -2.25, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25,
         1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75, 5.25, 5.75, 6.25, 6.75, 7.25, 7.75,
         8.25, 8.75, 9.25, 9.75, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5,
         19.5]

        flu_x = np.linspace(-19.95, 19.95, (400/self.res_mm))  # TODO get rid of hardcoding dimensions of 1mm res

        #my_flu = self.flip_fluences[index]
        my_flu = self.fluences[index]
        #first create interpolating object tmp
        tmp = interpl.RectBivariateSpline(flu_y, flu_x, my_flu,kx=1, ky=1, s=0)
        # tmp = np.clip(tmp, 0, 1, out=tmp)
        # now create new interpolated fluences and store
        self.interp_fluences[index] = np.clip(tmp(y_dim, x_dim),0,1)

    def make_interp(self,y_dim, x_dim):
        """y_dim must be 1D array containing co-ords in cms
        for fluence and x_dim 1D array likewise. x is parallel to leaf motion
        """
        flu_y = [-19.5, -18.5, -17.5, -16.5, -15.5, -14.5, -13.5, -12.5, -11.5, -10.5, -9.75,
         -9.25, -8.75, -8.25, -7.75, -7.25, -6.75, -6.25, -5.75, -5.25, -4.75, -4.25,
         -3.75, -3.25, -2.75, -2.25, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25,
         1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75, 5.25, 5.75, 6.25, 6.75, 7.25, 7.75,
         8.25, 8.75, 9.25, 9.75, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5,
         19.5]
        flu_x = np.linspace(-19.95, 19.95, (400/self.res_mm)) #TODO get rid of hardcoding dimensions of 1mm res

        # self.interp_fluences = list() # need to empty out list first
        self.interp_fluences = [None] * self.num_logs
        i = 0
        for flu in self.flip_fluences:

            #first create interpolating object tmp
            tmp = interpl.RectBivariateSpline(flu_y, flu_x, flu,kx=1, ky=1, s=0)
            #tmp = np.clip(tmp, 0, 1, out=tmp)

            # now create new interpolated fluences and store
            # self.interp_fluences.append(tmp(y_dim, x_dim))
            self.interp_fluences[i] = np.clip(tmp(y_dim, x_dim),0,1)
            i += 1
