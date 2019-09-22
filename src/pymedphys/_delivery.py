from pymedphys._base.delivery import DeliveryBase
from pymedphys._dicom.delivery import DeliveryDicom
from pymedphys._trf.delivery import DeliveryLogfile
from pymedphys._mudensity.delivery import DeliveryMuDensity
from pymedphys._mosaiq.delivery import DeliveryMosaiq


class Delivery(  # type: ignore
    DeliveryMosaiq, DeliveryMuDensity, DeliveryLogfile, DeliveryDicom, DeliveryBase
):
    pass
