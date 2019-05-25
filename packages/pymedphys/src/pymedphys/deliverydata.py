from pymedphys_base.deliverydata import DeliveryData as DeliveryDataBase

to_be_combined = [DeliveryDataBase]

try:
    from pymedphys_dicom.deliverydata import DeliveryDataDicom
    to_be_combined += [DeliveryDataDicom]
except ImportError:
    pass

try:
    from pymedphys_fileformats.deliverydata import DeliveryDataLogfile
    to_be_combined += [DeliveryDataLogfile]
except ImportError:
    pass

try:
    from pymedphys_mudensity.deliverydata import DeliveryDataMuDensity
    to_be_combined += [DeliveryDataMuDensity]
except ImportError:
    pass


class DeliveryData(*to_be_combined[::-1]):  # type: ignore
    pass
