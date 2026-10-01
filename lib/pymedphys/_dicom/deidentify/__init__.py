# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The DICOM de-identification engine.

The design is in ``docs/contrib/info/deidentification-design.md``. This
package does not yet de-identify anything; so far it holds the rule tables
generated from the DICOM standard and the code that loads them, and the
parts that later stages will use: the keys, keyed replacement UIDs, UID and
temporal attribute roles, patient pseudonyms, subject profiles, date
offsets, the actions of Table E.1-1 under selected options, the presets and
the validated policies composed from them, the checks of values against
their VR and VM, the zero-length and dummy values that the Z and D actions
write, the supplementary actions for attributes that Table E.1-1 omits,
including every text attribute that the supported IODs use, with their
actions under options, the classification of instances as de-identified or
sequestered, the names of the files and directories that output is written
to, the first pass's graph of the references between instances, a reader
that maps each byte of a written file to where it belongs, and the removal of
private attributes.
"""
