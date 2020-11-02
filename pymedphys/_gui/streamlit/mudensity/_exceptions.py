from pymedphys._streamlit.exceptions import (  # pylint: disable=unused-import
    NoRecordsFound,
)


class InputRequired(ValueError):
    pass


class WrongFileType(ValueError):
    pass


class UnableToCreatePDF(ValueError):
    pass


class NoControlPointsFound(ValueError):
    pass


class NoMosaiqAccess(ValueError):
    pass
