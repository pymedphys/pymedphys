from pymedphys._base.delivery import Delivery as DeliveryBase
from pymedphys._trf.decode.delivery import DeliveryLogfile
from pymedphys._mudensity.delivery import DeliveryMuDensity


class DeliveryDatabases(  # type: ignore
    DeliveryMuDensity, DeliveryLogfile, DeliveryBase
):
    pass
