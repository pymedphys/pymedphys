import warnings

WARNING = """
    It appears that the pseudonymise function as implemented has some
    identifying components able to be reversible. See
    <https://github.com/pymedphys/pymedphys/issues/1455> for more
    details.
    """

warnings.warn(WARNING)
