# Copyright (C) 2018 Simon Biggs

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


"""Calculate the MU Density given mu, mlc, and jaw control points.

.. WARNING::
    Although this is a useful tool in the toolbox for patient specific IMRT QA,
    in and of itself it is not a sufficient stand in replacement. This tool does
    not verify that the reported dose within the treatment planning system is
    delivered by the Linac.

    Deficiencies or limitations in the agreement between the treatment planning
    system's beam model and the Linac delivery will not be able to be
    highlighted by this tool. An example might be an overly modulated beam with
    many thin sweeping strips, the Linac may deliver those control points with
    positional accuracy but if the beam model in the TPS cannot sufficiently
    accurately model the dose effects of those MLC control points the dose
    delivery will not sufficiently agree with the treatment plan. In this case
    however, this tool will say everything is in agreement.

    It also may be the case that due to a hardware or calibration fault the
    Linac itself may be incorrectly reporting its MLC and/or Jaw postions. In
    this case the logfile record can agree exactly with the planned positions
    while the true real world positions be in significant deviation.

    The impact of these issues may be able to be limited by including with this
    tool an automated independent IMRT 3-D dose calculation tool as well as a
    daily automated MLC/jaw logfile to EPI to baseline agreement test that
    moves the EPI so as to measure the full set of leaf pairs and the full range
    of MLC and Jaw travel.

Available Functions
-------------------
>>> from pymedphys.mudensity import (
...     calc_mu_density, calc_single_control_point, single_mlc_pair, get_grid,
...     find_relevant_control_points, display_mu_density)
"""

# pylint: disable=W0401,W0614,W0611

from ._level0.libutils import clean_and_verify_levelled_modules

from ._level2.mudensity import *

clean_and_verify_levelled_modules(globals(), [
    '._level2.mudensity'
])
