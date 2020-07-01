"""Module docstring."""

from deprecated import deprecated as _deprecated

from . import dicom, electronfactors, mosaiq, mudensity, trf, wlutz
from ._data import data_path, zenodo_data_paths, zip_data_paths
from ._delivery import Delivery
from ._gamma.implementation.shell import gamma_shell as gamma
from ._trf.decode import read_trf as _read_trf
from ._version import __version__, version_info

read_trf = _deprecated(
    version="0.31.0", reason="This has been replaced with `pymedphys.trf.read`"
)(_read_trf)
