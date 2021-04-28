# Copyright (C) 2020 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
from typing import Tuple

from pymedphys._imports import numpy as np

from pymedphys import _losslessjpeg as lljpeg

from pymedphys._experimental.vendor.pylinac_vendored._pylinac_installed import (
    pylinac as _pylinac_installed,
)

from . import findbb, findfield, iview, pylinacwrapper
from .types import TwoNumbers

DEFAULT_LOW_SIGNAL_CUTOFF = 0.1  # Signal range is between 0.0 and 1.0.


def calculate(
    image_path,
    algorithm,
    bb_diameter,
    edge_lengths,
    penumbra,
    icom_field_rotation,
    fill_errors_with_nan=True,
    low_signal_cutoff=DEFAULT_LOW_SIGNAL_CUTOFF,
):
    x, y, image = load_iview_image(image_path)

    max_signal = np.max(image)
    if max_signal < low_signal_cutoff:
        if fill_errors_with_nan:
            return [np.nan, np.nan], [np.nan, np.nan]

        raise ValueError(
            f"The maximum signal within the image was {max_signal}. "
            "The `low_signal_cutoff` parameter has been set to "
            f"{low_signal_cutoff}."
        )

    ALGORITHM_FUNCTION_MAP = get_algorithm_function_map()

    calculate_function = ALGORITHM_FUNCTION_MAP[algorithm]
    field_centre, bb_centre = calculate_function(
        x=x,
        y=y,
        image=image,
        bb_diameter=bb_diameter,
        edge_lengths=edge_lengths,
        penumbra=penumbra,
        icom_field_rotation=icom_field_rotation,
        fill_errors_with_nan=fill_errors_with_nan,
    )

    return field_centre, bb_centre


@functools.lru_cache()
def get_algorithm_function_map():
    ALGORITHM_FUNCTION_MAP = {
        "PyMedPhys": pymedphys_wlutz_calculate,
        "PyMedPhys-LoosenedTolerance": _pymedphys_loosened_tolerance,
        "PyMedPhys-NoTolerance": _pymedphys_no_tolerance,
        f"PyLinac v{_pylinac_installed.__version__}": functools.partial(
            _pylinac_wlutz_calculate, pylinac_version=_pylinac_installed.__version__
        ),
        "PyLinac v2.2.6": functools.partial(
            _pylinac_wlutz_calculate, pylinac_version="2.2.6"
        ),
    }

    return ALGORITHM_FUNCTION_MAP


def load_iview_image(image_path):
    raw_image = lljpeg.imread(image_path)
    x, y, image = iview.iview_image_transform(raw_image)

    return x, y, image


def _pymedphys_loosened_tolerance(
    x: "np.ndarray",
    y: "np.ndarray",
    image: "np.ndarray",
    bb_diameter: float,
    edge_lengths: TwoNumbers,
    penumbra: float,
    icom_field_rotation: float,
    fill_errors_with_nan: bool = True,
    **_,
) -> Tuple[TwoNumbers, TwoNumbers]:
    bb_repeats = 10
    bb_consistency_tol = 0.5
    skip_pylinac = True

    return pymedphys_wlutz_calculate(
        x=x,
        y=y,
        image=image,
        bb_diameter=bb_diameter,
        edge_lengths=edge_lengths,
        penumbra=penumbra,
        icom_field_rotation=icom_field_rotation,
        fill_errors_with_nan=fill_errors_with_nan,
        bb_repeats=bb_repeats,
        bb_consistency_tol=bb_consistency_tol,
        skip_pylinac=skip_pylinac,
    )


def _pymedphys_no_tolerance(
    x: "np.ndarray",
    y: "np.ndarray",
    image: "np.ndarray",
    bb_diameter: float,
    edge_lengths: TwoNumbers,
    penumbra: float,
    icom_field_rotation: float,
    fill_errors_with_nan: bool = True,
    **_,
) -> Tuple[TwoNumbers, TwoNumbers]:
    bb_repeats = 1
    bb_consistency_tol = np.inf

    return pymedphys_wlutz_calculate(
        x,
        y,
        image,
        bb_diameter,
        edge_lengths,
        penumbra,
        icom_field_rotation,
        fill_errors_with_nan,
        bb_repeats,
        bb_consistency_tol,
    )


def pymedphys_wlutz_calculate(
    x: "np.ndarray",
    y: "np.ndarray",
    image: "np.ndarray",
    bb_diameter: float,
    edge_lengths: TwoNumbers,
    penumbra: float,
    icom_field_rotation: float,
    fill_errors_with_nan: bool = True,
    bb_repeats: int = findbb.DEFAULT_BB_REPEATS,
    bb_consistency_tol: float = findbb.DEFAULT_BB_CONSISTENCY_TOL,
    skip_pylinac=False,
    **_,
) -> Tuple[TwoNumbers, TwoNumbers]:
    """Utilise the PyMedPhys WLutz algorithm to determine the field
    centre and BB centre.

    Parameters
    ----------
    x : np.ndarray
        The x axis position definitions (mm) for the provided image
        pixels.
    y : np.ndarray
        The y axis position definitions (mm) for the provided image
        pixels.
    image : np.ndarray
        The image to be searched over.
    bb_diameter : float
        An estimate of the diameter of the ball-bearing (mm).
    edge_lengths : TwoNumbers
        The edge lengths of the radiation field (mm).
    penumbra : float
        An estimate of the distance between the nominal field edge and
        the nominal field shoulder (mm).
    icom_field_rotation : float
        The rotation of the collimator at the time the radiation image
        was captured. In degrees, in the same rotational coordinate
        system that is utilised by the Elekta iCom system.
    fill_errors_with_nan : bool, optional
        Whether or not to stop code execution when an internal error
        occurs. The default option is to march on but return
        ``[np.nan, np.nan]`` for the failing coordinates.
    bb_repeats : int, optional
        The number of times to attempt the ball bearing optimiser
        search, by default 2.
    bb_consistency_tol : float, optional
        The tolerance on the required internal consistency of the
        ball-bearing finding algorithm. The internal algorithm searches
        for multiple ball-bearings with a range of different sizes
        smaller than that provided by the user. If any predicted
        ``bb_centre`` deviates by more than this tolerance from the
        median ``bb_centre`` then if there are ``bb_repeats``
        available the initial conditions of the search are adjusted to
        begin at the new median and it is re-attempted. If
        ``bb_repeats`` have "run out" then depending on the
        ``fill_errors_with_nan`` parameter either an error is raised or
        ``[np.nan, np.nan]`` is returned. By default 0.2 mm.


    Returns
    -------
    field_centre : TwoNumbers
    bb_centre : TwoNumbers
    """

    nan_result: TwoNumbers = np.array([np.nan, np.nan])

    try:
        field_centre = findfield.find_field_centre(
            x, y, image, edge_lengths, penumbra, field_rotation=icom_field_rotation
        )
    except ValueError:
        if fill_errors_with_nan:
            field_centre = nan_result
            bb_centre = nan_result

            return field_centre, bb_centre
        else:
            raise

    try:
        bb_centre = findbb.find_bb_centre(
            x,
            y,
            image,
            bb_diameter,
            edge_lengths,
            penumbra,
            field_centre,
            field_rotation=icom_field_rotation,
            bb_repeats=bb_repeats,
            bb_consistency_tol=bb_consistency_tol,
            skip_pylinac=skip_pylinac,
        )
    except ValueError:
        if fill_errors_with_nan:
            bb_centre = nan_result
        else:
            raise

    return field_centre, bb_centre


def _pylinac_wlutz_calculate(
    x,
    y,
    image,
    edge_lengths,
    icom_field_rotation,
    pylinac_version,
    fill_errors_with_nan=True,
    **_,
):
    try:
        pylinac_results = pylinacwrapper.run_wlutz(
            x,
            y,
            image,
            edge_lengths,
            icom_field_rotation,
            find_bb=True,
            pylinac_versions=[pylinac_version],
            fill_errors_with_nan=fill_errors_with_nan,
        )

        field_centre = pylinac_results[pylinac_version]["field_centre"]
        bb_centre = pylinac_results[pylinac_version]["bb_centre"]

    except ValueError:
        if fill_errors_with_nan:
            field_centre = [np.nan, np.nan]
            bb_centre = [np.nan, np.nan]
        else:
            raise

    return field_centre, bb_centre
