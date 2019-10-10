from pymedphys._base.delivery import DeliveryBase
from pymedphys._dicom.delivery import DeliveryDicom
from pymedphys._mosaiq.delivery import DeliveryMosaiq
from pymedphys._mudensity.delivery import DeliveryMuDensity
from pymedphys._trf.delivery import DeliveryLogfile


class Delivery(  # type: ignore
    DeliveryMosaiq, DeliveryMuDensity, DeliveryLogfile, DeliveryDicom, DeliveryBase
):
    pass
