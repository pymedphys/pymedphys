# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

from pymedphys._imports import numpy as np
from pymedphys._imports import streamlit as st

from . import config as _config

# The pixel value written for NaN, which has no place on the vmin to vmax scale.
NAN_PIXEL_VALUE = 0


def normalize_and_convert_to_uint8(data, vmin, vmax):
    """Scale data linearly to the pixel values of an 8-bit greyscale image.

    ``vmin`` is written as 0 and ``vmax`` as 255. Values between them are
    scaled linearly and rounded down to a whole number. Values below ``vmin``
    are written as 0, and values above ``vmax`` as 255.

    NaN is written as 0 (``NAN_PIXEL_VALUE``), so in the image a NaN point
    looks the same as a point at or below ``vmin``.

    Parameters
    ----------
    data : numpy.ndarray
        The values to convert, of any shape.
    vmin, vmax : float
        The values written as 0 and as 255.

    Returns
    -------
    numpy.ndarray
        The pixel values, as ``uint8`` with the shape of ``data``.
    """
    # Normalize the data so that when data = vmin, norm=0 and when data=vmax, norm=1
    norm = (data - vmin) / (vmax - vmin)
    # Scale the data to suit a uint8 image
    img = 255 * norm
    # make sure there are no out of bound values
    img = np.clip(img, 0, 255)

    # NaN passes through the clip, and C does not define the result of
    # converting NaN to an integer: the value can differ between platforms,
    # and NumPy warns of an invalid value in the cast. Give NaN its pixel
    # value while the image is still floating point. The clip has already
    # brought infinities into range, so this replaces NaN alone.
    img = np.nan_to_num(img, nan=NAN_PIXEL_VALUE)

    # Convert the data to uint8 format
    img = img.astype(np.uint8)

    return img


def site_picker(config, radio_label, default=None, key=None):
    site_directories = _config.get_site_directories(config)

    site_options = list(site_directories.keys())

    if default is None:
        default_index = 0
    else:
        default_index = site_options.index(default)

    try:
        chosen_site = st.query_params["site"]
        if chosen_site not in site_options:
            st.error(
                f"Site provided through URL `{chosen_site}`, doesn't "
                "exist within `config.toml`. Please instead provide "
                f"one of `{site_options}`"
            )
            raise ValueError()
    except (KeyError, ValueError):
        chosen_site = _select_site(radio_label, site_options, default_index, key)

    return chosen_site


def _select_site(radio_label, site_options, default_index, key):
    chosen_site = st.radio(radio_label, site_options, index=default_index, key=key)

    return chosen_site


def get_site_and_directory(
    config, radio_label, directory_label, default=None, key=None
):
    site_directories = _config.get_site_directories(config)

    chosen_site = site_picker(config, radio_label, default=default, key=key)
    directory = site_directories[chosen_site][directory_label]

    return chosen_site, directory
