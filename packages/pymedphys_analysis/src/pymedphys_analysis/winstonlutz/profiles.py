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


def penumbra_flip_diff(profile, centre_to_test, field_width, penumbra_width):
    """Find sum of squares difference between penumbras when flipped

    Parameters
    ----------
    profile : function
        A function that has displacement as input, and profile value as output.
    centre_to_test : float
        A position to flip the profile about
    field_width : float
        The profile field width
    penumbra_width : float
        The profile penumbra width

    Returns
    -------
    sum_of_squares_diff : float
        The sum of squares difference between the field edges flipped about the
        provided centre.
    """
