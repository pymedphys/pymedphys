# pylint: disable = unused-import, missing-docstring

from deprecated import deprecated as _deprecated
from pymedphys._trf.decode import read_trf as _read
from pymedphys._trf.manage.identify import identify_logfile as identify

_read.__name__ = "`pymedphys.beta.trf.read`"
read = _deprecated(
    version="0.31.0",
    reason="This API has left beta. It is found at `pymedphys.trf.read`.",
)(_read)
