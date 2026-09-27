"""A DICOM toolbox."""

# pylint: disable = unused-import
# ruff: noqa: F401

import functools as _functools
import warnings as _warnings

from ._dicom.anonymise import anonymise_dataset as _anonymise_dataset
from ._dicom.anonymise.limitations import (
    LIMITATION_NOTICE as _LIMITATION_NOTICE,
)
from ._dicom.anonymise.limitations import AnonymisationLimitationWarning
from ._dicom.dose import (
    depth_dose,
    dicom_dose_interpolate,
    profile,
    zyx_and_dose_from_dataset,
)
from ._dicom.structure.merge import merge_contours


# The limitation warning is emitted here, at the public interface, so that the
# private implementation, which experimental pseudonymisation and the
# anonymise command also use, does not repeat it.
@_functools.wraps(_anonymise_dataset)
def anonymise(*args, **kwargs):
    _warnings.warn(_LIMITATION_NOTICE, AnonymisationLimitationWarning, stacklevel=2)
    return _anonymise_dataset(*args, **kwargs)


# functools.wraps copies the private module and name. Point them at the public
# name instead, so that pickle resolves it to this wrapper.
anonymise.__module__ = __name__
anonymise.__name__ = anonymise.__qualname__ = "anonymise"
