from pymedphys._vendor.deprecated import deprecated as _deprecated
from pymedphys.pinnacle import PinnacleExport as _PinnacleExport
from pymedphys.pinnacle import PinnacleImage as _PinnacleImage
from pymedphys.pinnacle import PinnaclePlan as _PinnaclePlan
from pymedphys.pinnacle import export_cli as _export_cli

_PinnacleExport.__name__ = "pymedphys.experimental.pinnacle.PinnacleExport"
PinnacleExport = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnacleExport`"
)(_PinnacleExport)

_export_cli.__name__ = "pymedphys.experimental.pinnacle.export_cli"
export_cli = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.export_cli`"
)(_export_cli)

_PinnacleImage.__name__ = "pymedphys.experimental.pinnacle.PinnacleImage"
PinnacleImage = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnacleImage`"
)(_PinnacleImage)

_PinnaclePlan.__name__ = "pymedphys.experimental.pinnacle.PinnaclePlan"
PinnaclePlan = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnaclePlan`"
)(_PinnaclePlan)
