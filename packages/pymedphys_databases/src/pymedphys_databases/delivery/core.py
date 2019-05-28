from pymedphys_base.delivery import Delivery as DeliveryBase
from pymedphys_fileformats.delivery import DeliveryLogfile
from pymedphys_mudensity.delivery import DeliveryMuDensity


class DeliveryDatabases(DeliveryMuDensity, DeliveryLogfile, DeliveryBase):  # type: ignore
    pass
