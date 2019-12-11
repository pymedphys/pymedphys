"""A suite of functions to determine the MU Density for a range of
formats

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
"""


# pylint: disable = unused-import

from ._mudensity.mudensity import calc_mu_density as calculate
from ._mudensity.mudensity import display_mu_density as display
from ._mudensity.mudensity import get_grid as grid
