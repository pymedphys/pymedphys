# Copyright (C) 2019 Cancer Care Associates

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


"""Expose a range of pymedphys, scipy, and numpy functions for use within
Excel via xlwings udf functionality.
"""

# pylint: disable=W0401,W0614


try:
    import xlwings as _
    HAS_XLWINGS = True
except ImportError:
    HAS_XLWINGS = False


if HAS_XLWINGS:
    from ..libutils import clean_and_verify_levelled_modules

    from ._level1.interpolate import *
    from ._level1.numpy import *
    from ._level1.dicom import *
    from ._level1.mephysto import *
    from ._level1.os_path import *

    clean_and_verify_levelled_modules(globals(), [
        '._level1.interpolate', '._level1.numpy', '._level1.dicom',
        '._level1.mephysto', '._level1.os_path'
    ], package='pymedphys.xlwings')
