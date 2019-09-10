try:
    from scipy.interpolate import RegularGridInterpolator
except ImportError:
    from .regulargrid import RegularGridInterpolator
