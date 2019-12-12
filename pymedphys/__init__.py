"""Module docstring."""

# pylint: disable = wrong-import-position

import lazy_import

LAZY_MODULES = (
    "matplotlib.pyplot",
    "matplotlib.path",
    "matplotlib",
    "numpy",
    "shapely.affinity",
    "shapely.geometry",
    "shapely",
    "pymssql",
    "jupyterlab_server",
    "keyring",
    "attr",
    "packaging",
    "yaml",
    "scipy.interpolate",
    "scipy.special",
    "scipy.optimize",
    "scipy.ndimage.measurements",
    "scipy.ndimage",
    "scipy.signal",
    "scipy",
    "pandas",
    "dbfread",
    "pydicom",
    "pynetdicom",
    "tqdm",
    "dateutil",
    "PIL",
    "imageio",
    "skimage",
)

for module_name in LAZY_MODULES:
    lazy_import.lazy_module(module_name)


from . import dicom, electronfactors, mosaiq, mudensity  # isort:skip
from ._data import data_path, zip_data_paths  # isort:skip
from ._delivery import Delivery  # isort:skip
from ._gamma.implementation.shell import gamma_shell as gamma  # isort:skip
from ._trf import read_trf  # isort:skip
from ._version import __version__, version_info  # isort:skip
