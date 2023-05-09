from pymedphys._vendor.deprecated import deprecated as _deprecated
from pymedphys.pinnacle import PinnacleExport as _PinnacleExport
from pymedphys.pinnacle import PinnacleImage as _PinnacleImage
from pymedphys.pinnacle import PinnaclePlan as _PinnaclePlan
from pymedphys.pinnacle import export_cli as _export_cli

PinnacleExport = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnacleExport`"
)(_PinnacleExport)

export_cli = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.export_cli`"
)(_export_cli)

PinnacleImage = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnacleImage`"
)(_PinnacleImage)

PinnaclePlan = _deprecated(
    reason="This has been replaced with `pymedphys.pinnacle.PinnaclePlan`"
)(_PinnaclePlan)
