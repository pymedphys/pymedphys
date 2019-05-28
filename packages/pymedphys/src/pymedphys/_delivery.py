from pymedphys_base.delivery import Delivery as DeliveryBase

to_be_combined = [DeliveryBase]

try:
    from pymedphys_dicom.delivery import DeliveryDicom
    to_be_combined += [DeliveryDicom]
except ImportError:
    pass

try:
    from pymedphys_fileformats.delivery import DeliveryLogfile
    to_be_combined += [DeliveryLogfile]
except ImportError:
    pass

try:
    from pymedphys_mudensity.delivery import DeliveryMuDensity
    to_be_combined += [DeliveryMuDensity]
except ImportError:
    pass


class Delivery(*to_be_combined[::-1]):  # type: ignore
    pass
