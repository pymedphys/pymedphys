class Shim:
    def __init__(self, import_error):
        self.import_error = import_error

    def __getattribute__(self, name):
        raise self.import_error


try:
    import pydicom

    pydicom.config.enforce_valid_values = True
except ImportError as e:
    pydicom = Shim(e)
