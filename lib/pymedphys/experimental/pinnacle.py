from pymedphys._vendor.deprecated import deprecated as _deprecated
from pymedphys.pinnacle import PinnacleExport as _PinnacleExport
from pymedphys.pinnacle import PinnacleImage as _PinnacleImage
from pymedphys.pinnacle import PinnaclePlan as _PinnaclePlan
from pymedphys.pinnacle import export_cli as _export_cli

# These objects are shared with the public API. Renaming them breaks autodoc,
# so the legacy path is named in each reason instead.
PinnacleExport = _deprecated(
    reason=(
        "`pymedphys.experimental.pinnacle.PinnacleExport` has been replaced "
        "with `pymedphys.pinnacle.PinnacleExport`"
    )
)(_PinnacleExport)

export_cli = _deprecated(
    reason=(
        "`pymedphys.experimental.pinnacle.export_cli` has been replaced "
        "with `pymedphys.pinnacle.export_cli`"
    )
)(_export_cli)

PinnacleImage = _deprecated(
    reason=(
        "`pymedphys.experimental.pinnacle.PinnacleImage` has been replaced "
        "with `pymedphys.pinnacle.PinnacleImage`"
    )
)(_PinnacleImage)

PinnaclePlan = _deprecated(
    reason=(
        "`pymedphys.experimental.pinnacle.PinnaclePlan` has been replaced "
        "with `pymedphys.pinnacle.PinnaclePlan`"
    )
)(_PinnaclePlan)
