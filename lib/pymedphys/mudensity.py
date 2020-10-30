"""A suite of functions to determine the MU Density for a range of
formats

.. WARNING::
   Although this is a useful tool in the toolbox for patient specific
   IMRT QA, in and of itself it is not a sufficient replacement for
   direct dosimetric measurement. This tool does not verify that the
   reported dose within the treatment planning system matches that
   delivered by the Linac.

   Deficiencies in a plan's agreement between the treatment planning
   system and the Linac due to deviations such as small field
   output factors or the MLC model will not be able to be picked up by
   this tool.

   Furthermore, when the MU Density is calculated off of log files alone
   this uses leaf and jaw positions as reported by the Linac which may
   not agree with their position in reality due to issues such as a
   hardware or calibration fault.
"""

# pylint: disable = unused-import

import textwrap

from ._mudensity.mudensity import calc_mu_density as calculate
from ._mudensity.mudensity import display_mu_density as display
from ._mudensity.mudensity import get_grid as grid

WARNING_MESSAGE = textwrap.dedent(__doc__.split("WARNING::")[-1])
