from pymedphys_base.deliverydata import DeliveryData as DeliveryDataBase
from pymedphys_fileformats.deliverydata import DeliveryDataLogfile
from pymedphys_mudensity.deliverydata import DeliveryDataMuDensity


class DeliveryDataDatabases(DeliveryDataMuDensity, DeliveryDataLogfile, DeliveryDataBase):  # type: ignore
    pass
