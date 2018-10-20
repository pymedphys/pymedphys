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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Tools to help facilitate the import style implemented by the PyMedPhys
library.
"""

from copy import copy


class ClobberCheck:
    """Used to check if `from package import *` clobbered any globals.

    Example:
        >>> from pymedphys._level1.importutilities import ClobberCheck

        >>> clobberCheck = ClobberCheck(globals())
        >>> from numpy import *
        >>> clobberCheck.baseline = globals()

        >>> an_unused_variable = 'foo'
        >>> clobberCheck.check(globals(), label="shouldn't trigger")

        >>> mean = 'bar'
        >>> try:
        ...     clobberCheck.check(globals(), label="After setting mean")
        ... except AssertionError as e:
        ...     print(e)
        [After setting mean] A global has been clobbered: `mean`
    """

    def __init__(self, input_globals):
        self.__original = copy(input_globals)
        self.__baseline = None
        self.__keys_to_check = None

    @property
    def baseline(self):
        """The reference set of globals to compare against.
        """
        return self.__baseline

    @baseline.setter
    def baseline(self, input_globals):
        self.__baseline = copy(input_globals)
        self.__keys_to_check = copy(
            set(self.__baseline).difference(set(self.__original)))

    def check(self, input_globals, label='No label'):
        """Run the check against the baseline.
        """
        keys_to_check = set(self.__baseline).difference(set(self.__original))

        for key in keys_to_check:
            assert self.__baseline[key] is input_globals[key], (
                "[{}] A global has been clobbered: `{}`".format(label, key)
            )
