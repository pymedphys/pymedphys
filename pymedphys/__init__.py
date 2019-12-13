"""Module docstring."""

# pylint: disable = wrong-import-position, no-name-in-module

import apipkg

apipkg.initpkg(
    __name__,
    {
        "dicom": "dicom",
        "electronfactors": "electronfactors",
        "mosaiq": "mosaiq",
        "mudensity": "mudensity",
        "data_path": "._data:data_path",
        "zip_data_paths": "._data:zip_data_paths",
        "Delivery": "._delivery:Delivery",
        "gamma": "._gamma.implementation.shell:gamma_shell",
        "read_trf": "._trf:read_trf",
        "__version__": "._version:__version__",
        "version_info": "._version:version_info",
    },
)

# This will never be true, but it helps pylint know what is going on
if "dicom" not in globals():
    from . import dicom, electronfactors, mosaiq, mudensity  # isort:skip
    from ._data import data_path, zip_data_paths  # isort:skip
    from ._delivery import Delivery  # isort:skip
    from ._gamma.implementation.shell import gamma_shell as gamma  # isort:skip
    from ._trf import read_trf  # isort:skip
    from ._version import __version__, version_info  # isort:skip
