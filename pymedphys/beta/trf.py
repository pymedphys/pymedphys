# pylint: disable = unused-import, missing-docstring

from pymedphys._trf.decode import read_trf as _read
from pymedphys._trf.manage.identify import identify_logfile as identify
from pymedphys._vendor.deprecated import deprecated as _deprecated

_read.__name__ = "pymedphys.beta.trf.read"
read = _deprecated(
    reason="This API has left beta. It is found at `pymedphys.trf.read`."
)(_read)
