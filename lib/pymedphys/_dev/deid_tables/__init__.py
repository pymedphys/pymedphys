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

"""Read de-identification rule tables from the published DICOM standard.

This development-only package reads NEMA's HTML (chtml) publication of the
standard, after checking each source file against its pinned SHA-256 digest,
as decision D-001 of the de-identification design requires. PyMedPhys ships
the tables generated from these sources, never the sources themselves.
"""
