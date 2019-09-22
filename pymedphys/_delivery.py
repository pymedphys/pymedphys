from pymedphys._base.delivery import DeliveryBase
from pymedphys._dicom.delivery import DeliveryDicom
from pymedphys._trf.delivery import DeliveryLogfile
from pymedphys._mudensity.delivery import DeliveryMuDensity


class Delivery(  # type: ignore
    DeliveryMuDensity, DeliveryLogfile, DeliveryDicom, DeliveryBase
):
    pass
