# pylint: disable = import-error, unused-import

import importlib

import pymedphys._vendor.apipkg

EXTERNAL_EXPORTS = (
    "matplotlib.pyplot",
    "matplotlib.path",
    "matplotlib.patches",
    "matplotlib.transforms",
    "matplotlib",
    "mpl_toolkits.mplot3d.art3d",
    "mpl_toolkits",
    "numpy",
    "shapely.affinity",
    "shapely.geometry",
    "shapely.ops",
    "shapely",
    "pymssql",
    "keyring",
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
    "pydicom.uid",
    "pydicom.dataset",
    "pydicom.sequence",
    "pydicom.filebase",
    "pydicom",
    "pynetdicom",
    "tqdm",
    "dateutil",
    "PIL",
    "imageio",
    "skimage.measure",
    "skimage.draw",
    "skimage",
    "requests",
    "attr",
    "watchdog.events",
    "watchdog.observers",
    "watchdog.observers.polling",
    "watchdog",
    "toml",
    "streamlit",
    "timeago",
    "libjpeg",
    "tkinter",
    "tkinter.filedialog",
    "tensorflow",
)

pymedphys._vendor.apipkg.initpkg(  # pylint: disable = protected-access
    __name__,
    {**{item: item for item in EXTERNAL_EXPORTS}, **{"plt": "matplotlib.pyplot"}},
)

THIS = importlib.import_module(__name__)
IMPORTABLES = dir(THIS)

# This will never actually run, but it helps pylint know what's going on
if "numpy" not in IMPORTABLES:
    import attr
    import dateutil
    import dbfread
    import keyring
    import libjpeg
    import packaging
    import pymssql
    import pynetdicom
    import requests
    import shapely
    import shapely.affinity
    import shapely.geometry
    import shapely.ops
    import streamlit
    import tensorflow
    import timeago
    import tkinter
    import tkinter.filedialog
    import toml
    import tqdm
    import watchdog
    import watchdog.events
    import watchdog.observers
    import watchdog.observers.polling
    import yaml

    import numpy
    import pandas
    import scipy
    import scipy.interpolate
    import scipy.ndimage
    import scipy.ndimage.measurements
    import scipy.optimize
    import scipy.signal
    import scipy.special

    import matplotlib
    import matplotlib.patches
    import matplotlib.path
    import matplotlib.pyplot
    import matplotlib.pyplot as plt
    import matplotlib.transforms
    import mpl_toolkits
    import mpl_toolkits.mplot3d.art3d

    import imageio
    import PIL
    import skimage
    import skimage.draw
    import skimage.measure

    import pydicom
    import pydicom.dataset
    import pydicom.filebase
    import pydicom.sequence
    import pydicom.uid

    raise ValueError("This section of code should never run")
