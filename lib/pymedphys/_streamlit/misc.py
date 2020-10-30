# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name

import streamlit as st

from . import config


def site_picker(radio_label, default=None, key=None):
    site_directories = config.get_site_directories()
    site_options = list(site_directories.keys())

    if default is None:
        default_index = 0
    else:
        default_index = site_options.index(default)
    chosen_site = st.radio(radio_label, site_options, index=default_index, key=key)

    return chosen_site


def get_site_and_directory(radio_label, directory_label, default=None, key=None):
    site_directories = config.get_site_directories()

    chosen_site = site_picker(radio_label, default=default, key=key)
    directory = site_directories[chosen_site][directory_label]

    return chosen_site, directory
