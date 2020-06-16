# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def filter_ct_uids(
    structure_uid_to_ct_uids,
    structure_names_by_structure_set_uid,
    structure_names_by_ct_uid,
    study_set_must_have_all_of,
    slice_at_least_one_of,
    slice_must_have,
    slice_cannot_have,
):
    filtered_ct_uids = []

    for structure_uid, ct_uids in structure_uid_to_ct_uids.items():
        structure_names_in_study_set = set(
            structure_names_by_structure_set_uid[structure_uid]
        )

        if not structure_names_in_study_set.issuperset(study_set_must_have_all_of):
            continue

        for ct_uid in ct_uids:
            try:
                structure_names_on_slice = set(structure_names_by_ct_uid[ct_uid])
            except KeyError:
                structure_names_on_slice = set([])

            if len(structure_names_on_slice.intersection(slice_at_least_one_of)) == 0:
                continue

            if not structure_names_on_slice.issuperset(slice_must_have):
                continue

            if len(structure_names_on_slice.intersection(slice_cannot_have)) != 0:
                continue

            filtered_ct_uids.append(ct_uid)

    return filtered_ct_uids
