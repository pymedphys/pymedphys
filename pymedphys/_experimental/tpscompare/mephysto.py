# Copyright (C) 2016 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import numpy as np

import scipy.interpolate

from pymedphys.labs.fileformats.mephysto import load_mephysto

from .normalisation import normalise_profile


def mephysto_absolute_depth_dose(
    absolute_dose, depth_of_absolute_dose_mm, distance, relative_dose, scan_curvetype
):
    choose_mephysto = scan_curvetype == "PDD"
    if np.sum(choose_mephysto) != 1:
        raise ValueError("Can only handle one PDD per mephysto file")

    mephysto_pdd_depth = distance[choose_mephysto][0]
    mephysto_dose = relative_dose[choose_mephysto][0]

    interpolation = scipy.interpolate.interp1d(mephysto_pdd_depth, mephysto_dose)

    mephysto_pdd_dose = (
        mephysto_dose / interpolation(depth_of_absolute_dose_mm) * absolute_dose
    )

    return mephysto_pdd_depth, mephysto_pdd_dose


def mephysto_absolute_profiles(
    curvetype,
    depth_test,
    distance,
    relative_dose,
    scan_curvetype,
    scan_depth,
    mephysto_pdd_depth,
    mephysto_pdd_dose,
):

    choose_mephysto = (scan_curvetype == curvetype) & (scan_depth == depth_test)

    if np.sum(choose_mephysto) != 1:
        raise ValueError("Can only handle exactly one scan type per mephysto file")

    mephysto_distance = distance[choose_mephysto][0]
    mephysto_normalised_dose = normalise_profile(
        mephysto_distance,
        relative_dose[choose_mephysto][0],
        scale_to_pdd=True,
        pdd_distance=mephysto_pdd_depth,
        pdd_relative_dose=mephysto_pdd_dose,
        scan_depth=depth_test,
    )

    return mephysto_distance, mephysto_normalised_dose


def absolute_scans_from_mephysto(
    mephysto_file, absolute_dose, depth_of_absolute_dose_mm
):
    distance, relative_dose, scan_curvetype, scan_depth = load_mephysto(mephysto_file)

    depth_testing = scan_depth[~np.isnan(scan_depth)]
    depth_testing = np.unique(depth_testing)

    if depth_of_absolute_dose_mm == "dmax":
        choose_mephysto = scan_curvetype == "PDD"
        mephysto_pdd_depth = distance[choose_mephysto][0]
        mephysto_dose = relative_dose[choose_mephysto][0]
        depth_of_absolute_dose_mm = mephysto_pdd_depth[np.argmax(mephysto_dose)]

    mephysto_pdd_depth, mephysto_pdd_dose = mephysto_absolute_depth_dose(
        absolute_dose,
        depth_of_absolute_dose_mm,
        distance,
        relative_dose,
        scan_curvetype,
    )

    scans = {
        "depth_dose": {"displacement": mephysto_pdd_depth, "dose": mephysto_pdd_dose},
        "profiles": {},
    }

    for depth_test in depth_testing:
        (
            mephysto_distance_inplane,
            mephysto_normalised_dose_inplane,
        ) = mephysto_absolute_profiles(
            "INPLANE_PROFILE",
            depth_test,
            distance,
            relative_dose,
            scan_curvetype,
            scan_depth,
            mephysto_pdd_depth,
            mephysto_pdd_dose,
        )

        (
            mephysto_distance_crossplane,
            mephysto_normalised_dose_crossplane,
        ) = mephysto_absolute_profiles(
            "CROSSPLANE_PROFILE",
            depth_test,
            distance,
            relative_dose,
            scan_curvetype,
            scan_depth,
            mephysto_pdd_depth,
            mephysto_pdd_dose,
        )

        scans["profiles"][depth_test] = {
            "inplane": {
                "displacement": mephysto_distance_inplane,
                "dose": mephysto_normalised_dose_inplane,
            },
            "crossplane": {
                "displacement": mephysto_distance_crossplane,
                "dose": mephysto_normalised_dose_crossplane,
            },
        }

    return scans
