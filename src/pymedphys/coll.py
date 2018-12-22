# Copyright (C) 2018 PyMedPhys Contributors

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

"""Various helper functions for mlcs and jaws.

Available Functions
-------------------
>>> from pymedphys.coll import (
...    calc_mu_density, mlc_equivalent_square_fs)
"""

# pylint: disable=W0401,W0614,C0413,W0611

from ._level0.libutils import clean_and_verify_levelled_modules

from ._level1.collmlctypes import *
from ._level2.collequivalent import *
from ._level2.collmudensity import *

clean_and_verify_levelled_modules(globals(), [
    '._level1.collmlctypes', '._level2.collequivalent',
    '._level2.collmudensity'
])

from ._level2 import collmudensity  # nopep8
