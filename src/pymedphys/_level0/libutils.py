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


"""Tools to help facilitate the import style implemented by the PyMedPhys
library.
"""

import importlib
from copy import copy


def clean_and_verify_levelled_modules(input_globals, module_names):
    all_new_definitions = []

    scope = {}
    scope['IMPORTS'] = None

    clobber_check = ClobberCheck(ignore=['IMPORTS'])
    new_definitions = NewDefinitions()

    for module_name in module_names:
        clobber_check.baseline = scope
        new_definitions.baseline = scope

        module = importlib.import_module(
            module_name, package='pymedphys')
        for key, item in module.__dict__.items():
            if not key.startswith('_'):
                scope[key] = item

        clobber_check.check(scope, label=module_name)
        all_new_definitions += new_definitions.find(
            scope, module.IMPORTS)

    for key in copy(input_globals):
        if (key not in all_new_definitions) and (not key.startswith('_')):
            del input_globals[key]


class NewDefinitions:
    def __init__(self):
        self.__baseline = None

    @property
    def baseline(self):
        """The reference set of globals to compare against.
        """
        return self.__baseline

    @baseline.setter
    def baseline(self, input_globals):
        self.__baseline = copy(input_globals)

    def find(self, input_globals, imports):
        """Run the check against the baseline.
        """

        new_definitions = []
        for key in input_globals.keys():
            if (key not in self.__baseline) and (key not in imports):
                new_definitions.append(key)

        return new_definitions


def get_imports(input_globals):
    input_globals_copy = copy(input_globals)
    public_imports = [
        item for item in input_globals_copy if not item.startswith('_')]

    return public_imports


class ClobberCheck:
    """Used to check if `from package import *` clobbered any globals.

    Examples:
        Basic usage

        In it's rawest form `ClobberCheck` is simply checking to see if any
        global has changed since it was last baselined:

        >>> from pymedphys.libutils import ClobberCheck
        >>> clobberCheck = ClobberCheck()

        >>> a_variable = 5

        >>> clobberCheck.baseline = globals()
        >>> a_variable = 6

        >>> try:
        ...     clobberCheck.check(globals(), label="Changing a_variable")
        ... except AssertionError as e:
        ...     print(e)
        Changing a_variable clobbered the following:
        ['a_variable']


        New variables can be assigned, as long as they don't overwrite an old
        one:

        >>> clobberCheck.baseline = globals()

        >>> a_new_variable = 10
        >>> clobberCheck.check(globals())


        Reassigning the variable to the same object doesn't tigger the
        assertion either:

        >>> a_variable = 6
        >>> clobberCheck.check(globals())


        Intendend usage

        The design of this class is to verify whether or not importing a
        package using `*` overwrote any definitions:

        >>> from pymedphys.libutils import ClobberCheck
        >>> clobberCheck = ClobberCheck()

        >>> from numpy import *
        >>> clobberCheck.baseline = globals()

        >>> from pandas import *
        >>> try:
        ...     clobberCheck.check(globals(), label="Importing pandas")
        ... except AssertionError as e:
        ...     print(e)
        Importing pandas clobbered the following:
        ['unique']


        It can also detect if you yourself have clobbered a global as so:

        >>> from pymedphys.libutils import ClobberCheck

        >>> clobberCheck = ClobberCheck()
        >>> from numpy import *
        >>> clobberCheck.baseline = globals()

        >>> an_unused_variable = 'foo'
        >>> clobberCheck.check(globals())

        >>> mean = 'bar'
        >>> sum = 'foobar'

        >>> try:
        ...     clobberCheck.check(globals(), label="Reassigning mean and sum")
        ... except AssertionError as e:
        ...     print(e)
        Reassigning mean and sum clobbered the following:
        ['mean', 'sum']
    """

    def __init__(self, ignore=[]):
        self.__baseline = None
        self.__ignore = ignore

    @property
    def baseline(self):
        """The reference set of globals to compare against.
        """
        return self.__baseline

    @baseline.setter
    def baseline(self, input_globals):
        self.__baseline = copy(input_globals)

    def check(self, input_globals, label='You have'):
        """Run the check against the baseline.
        """

        clobbered_variables = []
        for key, a_global in self.__baseline.items():
            if (key not in self.__ignore) and (a_global is not input_globals[key]):
                clobbered_variables.append(key)

        clobbered_variables.sort()

        assert not clobbered_variables, (
            "{} clobbered the following:\n{}".format(
                label, clobbered_variables)
        )
