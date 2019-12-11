"""Module docstring."""

import apipkg

apipkg.initpkg(
    __name__,
    {
        "data_path": "._data:data_path",
        "zip_data_paths": "._data:zip_data_paths",
        "Delivery": "._delivery:Delivery",
        "gamma": "._gamma.implementation.shell:gamma_shell",
        "read_trf": "._trf:read_trf",
        "__version__": "._version:__version__",
        "version_info": "._version:version_info",
    },
)

from . import (  # isort:skip pylint:disable = wrong-import-position
    dicom,
    electronfactors,
    mosaiq,
    mudensity,
)
