from ._vendor.deprecated import deprecated as _deprecated
from .metersetmap import WARNING_MESSAGE as _WARNING_MESSAGE
from .metersetmap import calculate as _calculate
from .metersetmap import display as _display
from .metersetmap import grid as _grid

_calculate.__name__ = "pymedphys.mudensity.calculate"
calculate = _deprecated(
    reason="This has been replaced with `pymedphys.metersetmap.calculate`"
)(_calculate)

_display.__name__ = "pymedphys.mudensity.display"
display = _deprecated(
    reason="This has been replaced with `pymedphys.metersetmap.display`"
)(_display)

_grid.__name__ = "pymedphys.mudensity.grid"
grid = _deprecated(reason="This has been replaced with `pymedphys.metersetmap.grid`")(
    _grid
)

WARNING_MESSAGE = _WARNING_MESSAGE
