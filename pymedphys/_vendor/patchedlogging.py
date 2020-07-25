# https://github.com/python/cpython/blob/a667e1c66a62d509c39d30abf11778213a1e1ca0/Lib/logging/__init__.py#L1896-L1999

import logging

_basicConfig = logging.basicConfig


def basicConfig(**kwargs):
    force = kwargs.pop("force", False)
    if force:
        for h in logging.root.handlers[:]:  # pylint: disable = no-member
            logging.root.removeHandler(h)  # pylint: disable = no-member
            h.close()

    _basicConfig(**kwargs)


logging.basicConfig = basicConfig
