from pymedphys._base.delivery import DeliveryBase
from pymedphys._trf.delivery import DeliveryLogfile
from pymedphys._mudensity.delivery import DeliveryMuDensity


class DeliveryDatabases(  # type: ignore
    DeliveryMuDensity, DeliveryLogfile, DeliveryBase
):
    pass
