"""Module docstring."""

from . import dicom, metersetmap, mosaiq, mudensity, trf
from ._data import data_path, zenodo_data_paths, zip_data_paths
from ._delivery import Delivery
from ._gamma.implementation.shell import gamma_shell as gamma
from ._trf.decode import read_trf as _read_trf
from ._vendor.deprecated import deprecated as _deprecated
from ._version import __version__, version_info

_read_trf.__name__ = "pymedphys.read_trf"
read_trf = _deprecated(reason="This has been replaced with `pymedphys.trf.read`")(
    _read_trf
)
