# Copyright 2001-2017 by Vinay Sajip. All Rights Reserved.
#
# Permission to use, copy, modify, and distribute this software and its
# documentation for any purpose and without fee is hereby granted,
# provided that the above copyright notice appear in all copies and that
# both that copyright notice and this permission notice appear in
# supporting documentation, and that the name of Vinay Sajip
# not be used in advertising or publicity pertaining to distribution
# of the software without specific, written prior permission.
# VINAY SAJIP DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE, INCLUDING
# ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
# VINAY SAJIP BE LIABLE FOR ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR
# ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER
# IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT
# OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# Code vendored from:
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
