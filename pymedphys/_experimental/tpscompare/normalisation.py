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

from scipy.interpolate import interp1d
from scipy.signal import savgol_filter


def normalise(
    distance,
    relative_dose,
    scan_curvetype,
    scan_depth,
    pdd_normalisation_depth=None,
    profile_normalisation_position=None,
    scale_to_pdd=False,
    smoothed_normalisation=False,
):
    """Take a series of PDDs and/or profiles and normalise them according to
    a range of available options.
    """
    # Convert scan_curvetype to a numpy array
    scan_curvetype = np.array(scan_curvetype)

    # Find the references of PDDs and profiles
    ref_of_pdd = np.where(scan_curvetype == "PDD")[0]
    ref_of_profile = np.where(
        (scan_curvetype == "INPLANE_PROFILE") | (scan_curvetype == "CROSSPLANE_PROFILE")
    )[0]

    # Step through each PDD and normalise them
    for i in ref_of_pdd:
        relative_dose[i] = normalise_pdd(
            relative_dose[i],
            depth=distance[i],
            normalisation_depth=pdd_normalisation_depth,
        )

    # If user requested scaling to PDD run "normalise" profile with relevant
    # options
    if scale_to_pdd:
        pdd_distance = distance[ref_of_pdd[0]]
        pdd_relative_dose = relative_dose[ref_of_pdd[0]]

        for i in ref_of_profile:
            relative_dose[i] = normalise_profile(
                distance[i],
                relative_dose[i],
                pdd_distance=pdd_distance,
                pdd_relative_dose=pdd_relative_dose,
                scan_depth=scan_depth[i],
                normalisation_position=profile_normalisation_position,
                smoothed_normalisation=smoothed_normalisation,
                scale_to_pdd=True,
            )
    # If user did not request PDD scaling run normalise_profile with basic
    # options
    else:
        for i in ref_of_profile:
            relative_dose[i] = normalise_profile(
                distance[i],
                relative_dose[i],
                normalisation_position=profile_normalisation_position,
                smoothed_normalisation=smoothed_normalisation,
            )

    return relative_dose


def normalise_pdd(
    relative_dose, depth=None, normalisation_depth=None, smoothed_normalisation=False
):
    """Normalise a pdd at a given depth. If normalisation_depth is left
    undefined then the depth of dose maximum is used for the normalisation
    depth.
    """

    if smoothed_normalisation:
        filtered = savgol_filter(relative_dose, 21, 2)
    else:
        filtered = relative_dose

    # normalisation_depth will be None if the user does not define it, if that
    # is the case simply define normalisation by 100 / the maximum value
    if normalisation_depth is None:
        normalisation = 100 / np.max(filtered)

    # However if the user did define a normalisation depth then need to
    # interpolate using the provided depth variable to find the relative dose
    # value to normalise to
    else:
        if depth is None:
            raise Exception(
                "distance variable needs to be defined to normalise to a " "depth"
            )
        interpolation = interp1d(depth, filtered)
        normalisation = 100 / interpolation(normalisation_depth)

    return relative_dose * normalisation


def normalise_profile(
    distance,
    relative_dose,
    pdd_distance=None,
    pdd_relative_dose=None,
    scan_depth=None,
    normalisation_position="cra",
    scale_to_pdd=False,
    smoothed_normalisation=False,
):
    """Normalise a profile given a defined normalisation position and
    normalisation scaling
    """
    # If scaling is to PDD interpolate along the PDD to find the scaling,
    # otherwise set scaling to 100.
    if scale_to_pdd:
        # If insufficient information has been supplies raise a meaningful
        # error
        if pdd_distance is None or pdd_relative_dose is None or scan_depth is None:
            raise Exception(
                "Scaling to PDD requires pdd_distance, pdd_relative_dose, "
                "and scan_depth to be defined."
            )

        pdd_interpolation = interp1d(pdd_distance, pdd_relative_dose)
        scaling = pdd_interpolation(scan_depth)
    else:
        scaling = 100

    # Linear interpolation function
    if smoothed_normalisation:
        filtered = savgol_filter(relative_dose, 21, 2)
        interpolation = interp1d(distance, filtered)
    else:
        interpolation = interp1d(distance, relative_dose)

    try:
        # Check if user wrote a number for normalisation position
        float_position = float(normalisation_position)
    except ValueError:
        # If text was written the conversion to float will fail
        float_position = None

    # If position was given by the user as a number then define the
    # normalisation to that position
    if float_position is not None:
        normalisation = scaling / interpolation(float_position)

    # Otherwise if the user gave 'cra' (case independent) normalise at 0
    elif normalisation_position.lower() == "cra":
        normalisation = scaling / interpolation(0)

    # Otherwise if the user gave 'cm' (case independent) normalise to the
    # centre of mass
    elif normalisation_position.lower() == "cm":
        threshold = 0.5 * np.max(relative_dose)
        weights = relative_dose.copy()
        weights[weights < threshold] = 0

        centre_of_mass = np.average(distance, weights=weights)
        normalisation = scaling / interpolation(centre_of_mass)

    # Otherwise if the user gave 'max' (case independent) normalise to the
    # point of dose maximum
    elif normalisation_position.lower() == "max":
        normalisation = scaling / np.max(relative_dose)

    else:
        raise TypeError(
            "Expected either a float for `normalisation_position` "
            "or one of 'cra', 'cm', or 'max'"
        )

    return relative_dose * normalisation
