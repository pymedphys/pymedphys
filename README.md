# PyMedPhys

## Description

A range of python modules encompased under the pymedphys package, designed to
be built upon for Medical Physics applications.

## Alpha stage development

These libraries are currently under alpha level development. Be cautious with
code in this library. Not only might code depending on it break, but the
results given by this code likely may just be plain wrong.

This will be true throughout the alpha stage development of these libraries.
This notice will be adjusted once this should no longer be the case.

Throughout the lifetime of this library however the following will always be
true:

> In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, unless required by applicable law (such as deliberate and grossly negligent acts) or agreed to in writing, shall any Contributor be liable to You for damages, including any direct, indirect, special, incidental, or consequential damages of any character arising as a result of this License or out of the use or inability to use the Work (including but not limited to damages for loss of goodwill, work stoppage, computer failure or malfunction, or any and all other commercial damages or losses), even if such Contributor has been advised of the possibility of such damages.

## Installation

This package is available on pypi at https://pypi.org/project/pymedphys/.

Install this package by running the following:

```bash
pip install pymedphys
```

## Team and copyright

The aim of PyMedPhys is that it will be developed by an open community of contributors.
We use a shared copyright model that enables all contributors to maintain the copyright on their
contributions. All code is licensed under the AGPLv3+ with additional terms from the Apache-2.0 license.

PyMedPhys' current maintainers listed in alphabetical order, with affilliation, and main area of contribution:

* [Anthony Bisulco](https://github.com/anthonytec2), [Brookhaven National Laboratory](https://www.bnl.gov/world/), Collapsed Cone Convolution
* [Matthew Sobolewski](https://github.com/msobolewski), [Cancer Care Associates](http://cancercare.com.au/), Medical Physics Overview
* [Simon Biggs](https://github.com/SimonBiggs), [Cancer Care Associates](http://cancercare.com.au/), General Development

### License agreement

Copyright (C) 2018 PyMedPhys Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version (the "AGPL-3.0+").

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License and the additional terms for more
details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.

ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
Affrero General Public License. These aditional terms are Sections 1, 5,
6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
where all references to the definition "License" are instead defined to
mean the AGPL-3.0+.

You should have received a copy of the Apache-2.0 along with this
program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

## Cyclic dependencies and the justification of file structure

If package A depends on package B, and package B depends on package C, it is
important that package C does not then depend on package A. This is called a
cyclic dependency. It causes issues in dependency logic and can be avoided
by purposefully designing how the packages depend on one another.

Ideally library packages are split up module by module based upon single tasks
that each library achieves. By having a very large number of small single
purpose modules the dependency tree can become very complicated. Complicated
dependency trees do not scale. As a result the inter dependencies between
library packages is tightly regulated. The modules themselves need to be
designed and programmed with these restrictions in mind.

The physical design of the module dependencies is inspired by
John Lakos at Bloomberg, writer of Large-Scale C++ Software Design. He
describes this methodology in a talk he gave which is available on YouTube:

> <https://youtu.be/QjFpKJ8Xx78?t=41m7s>

### Level 1

Level 1 packages are the foundation library packages.

These packages SHALL NOT depend on any internal package. They MAY however
depend on external packages (Level 0).

Given that these Level 1 packages are foundation packages their external
packages SHOULD only ever be those that are in wide use and are highly
supported within the python community. Examples of reasonable external packages
to be used are numpy, scipy, and pandas.

### Level 2

Level 2 packages.

The internal packages that Level 2 packages depend on SHALL only be Level 1
packages or external packages as long as those external
packages don't intern depend on one defined within this group.

### Level 3

Level 3 packages.

The internal packages that these depend on SHALL only be Level 1 or Level 2.
They MAY also depend external packages as long as those external
packages don't intern depend on one defined within this group.
