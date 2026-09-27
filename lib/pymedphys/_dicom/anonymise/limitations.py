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

"""The limitation notice shared by the anonymise function and command."""

LIMITATION_NOTICE = (
    "pymedphys.dicom.anonymise replaces only a list of attributes. Its "
    "default list keeps every UID and most RT attributes, such as plan, "
    "structure set, ROI, and beam labels and names, and machine names; it does "
    "not rebuild the file preamble or File Meta Information; and the command "
    "names its output files after the original SOP Instance UID. Its output "
    "can still identify patients, so review it before sharing it. See "
    "https://docs.pymedphys.com/en/latest/users/background/"
    "dicom-deidentification.html"
)


class AnonymisationLimitationWarning(UserWarning):
    """``pymedphys.dicom.anonymise`` has known limitations.

    This is not a deprecation warning. No replacement is available yet, so
    ``pymedphys.dicom.anonymise`` is not scheduled for removal (decision
    D-019 in the de-identification design document).
    """
