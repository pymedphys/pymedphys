# Copyright (C) 2018 Paul King

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
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

# import os

# import numpy as np

# from pymedphys_fileformats.profiler import write_prs

# DATA_DIRECTORY = os.path.join(
#     os.path.dirname(__file__), "../data/devices/profiler")


# def test_write_prs():

#     y_vals = [-16.4 + 0.4*i for i in range(83)]
#     x_vals = [-11.2 + 0.4*i for i in range(57)]

#     # UNIFORM DOSE 100 CGY
#     out_file = os.path.join(DATA_DIRECTORY, 'UNIFORM_DOSE_100_CGY.prs')
#     base_file = os.path.join(DATA_DIRECTORY, 'UNIFORM_DOSE_100_CGY.npy')
#     y_dose = [100.0]*83
#     x_dose = [100.0]*57
#     dose = y_dose + x_dose
#     y_prof = list(zip(y_vals, dose[:83]))
#     x_prof = list(zip(x_vals, dose[83:]))
#     result = write_prs(x_prof, y_prof, file_name=out_file)
#     # np.save(base_file, result)
#     assert np.all(result == np.load(base_file))

#     # PULSE 2D 100 CGY 10X10
#     out_file = os.path.join(DATA_DIRECTORY, 'PULSE_2D_100_CGY_10X10.prs')
#     base_file = os.path.join(DATA_DIRECTORY, 'PULSE_2D_100_CGY_10X10.npy')
#     y_dose = [0.0]*29 + [100.0]*25 + [0.0]*29
#     x_dose = [0.0]*16 + [100.0]*25 + [0.0]*16
#     dose = y_dose + x_dose
#     y_prof = list(zip(y_vals, dose[:83]))
#     x_prof = list(zip(x_vals, dose[83:]))
#     result = write_prs(x_prof, y_prof, file_name=out_file)
#     # np.save(base_file, result)
#     assert np.all(result == np.load(base_file))

#     # UNSAMPLED PULSE 100 CGY
#     out_file = os.path.join(DATA_DIRECTORY, 'UNSAMPLED_PULSE_100_CGY.prs')
#     base_file = os.path.join(DATA_DIRECTORY, 'UNSAMPLED_PULSE_100_CGY.npy')
#     pulse = [(-50, 0), (-5.1, 0), (-4.9, 100), (4.9, 100), (5.1, 0), (50, 0)]
#     result = write_prs(pulse, pulse, file_name=out_file)
#     # np.save(base_file, result)
#     assert np.all(result == np.load(base_file))

#     # TOO SHORT PULSE
#     out_file = os.path.join(DATA_DIRECTORY, 'TOO_SHORT_PULSE.prs')
#     base_file = os.path.join(DATA_DIRECTORY, 'TOO_SHORT_PULSE.npy')
#     pulse = [(-10, 0), (-5.1, 0), (-4.9, 100), (4.9, 100), (5.1, 0), (10, 0)]
#     result = write_prs(pulse, pulse, file_name=out_file)
#     # np.save(base_file, result)
#     assert np.all(result == np.load(base_file))
