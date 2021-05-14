# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

from pymedphys._imports import streamlit as st

from . import config as _config


def site_picker(config, radio_label, default=None, key=None):
    site_directories = _config.get_site_directories(config)

    site_options = list(site_directories.keys())

    if default is None:
        default_index = 0
    else:
        default_index = site_options.index(default)

    try:
        chosen_site = st.experimental_get_query_params()["site"][0]
        if not chosen_site in site_options:
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
