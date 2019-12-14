# Copyright (c) 2014-2019 James Kerns

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

# Vendored from https://github.com/jrkerns/pylinac/tree/698254258ff4cb87812840c42b34c93ae32a4693

# The following is adapted from: http://code.activestate.com/recipes/578809-decorator-to-check-method-param-types/
# Another type checking decorator: http://code.activestate.com/recipes/454322-type-checking-decorator/


# pylint: disable = unidiomatic-typecheck

import time
from abc import ABCMeta
from functools import wraps
from inspect import signature

from pymedphys._imports import numpy as np


def timethis(func):
    """Report execution time of function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(func.__name__, f"took {end-start:3.2f}s")
        return result

    return wrapper


def type_accept(*type_args, **type_kwargs):
    """Decorator to check function/method input types. Based on Python Cookbook 3rd ed. #9.7."""

    def decorate(func):

        # Map function argument names to supplied types
        sig = signature(func)
        bound_types = sig.bind_partial(*type_args, **type_kwargs).arguments

        @wraps(func)
        def wrapper(*args, **kwargs):
            bound_values = sig.bind(*args, **kwargs)
            # Enforce type assertions across supplied arguments
            for name, value in bound_values.arguments.items():
                if name in bound_types:
                    if type(bound_types[name]) in (
                        type,
                        ABCMeta,
                    ):  # Single-type comparisons
                        if not isinstance(value, bound_types[name]):
                            raise TypeError(
                                f"Argument '{name}' must be {bound_types[name]}"
                            )
                    else:
                        if type(value) not in bound_types[name]:
                            if value not in bound_types[name]:
                                raise TypeError(
                                    f"Argument '{name}' must be {bound_types[name]}"
                                )
            return func(*args, **kwargs)

        return wrapper

    return decorate


def value_accept(*value_args, **value_kwargs):
    """Decorator to check function/method input types. Based on Python Cookbook 3rd ed. #9.7."""

    def decorate(func):
        sig = signature(func)
        # convert any dictionary value acceptances to tuples
        vkw = convert_dictvals2tuple(value_kwargs)
        # Map function argument names to supplied types
        bound_values = sig.bind_partial(*value_args, **vkw).arguments

        @wraps(func)
        def wrapper(*args, **kwargs):
            passed_values = sig.bind(*args, **kwargs)
            # Enforce value assertions across supplied arguments
            for name, value in passed_values.arguments.items():
                if name in bound_values:
                    if type(value) in (float, int, np.float64):
                        # value must be within a number range
                        if not bound_values[name][0] <= value <= bound_values[name][1]:
                            raise ValueError(
                                f"Argument '{name}' needs to be between {bound_values[name][0]:f} and {bound_values[name][1]:f}"
                            )
                    else:
                        # value is a str and must be one of the accepted str values
                        if value not in bound_values[name]:
                            raise ValueError(
                                f"Argument '{name}' must be one of {bound_values[name]}"
                            )
            return func(*args, **kwargs)

        return wrapper

    return decorate


def convert_dictvals2tuple(args):
    """Convert from dictionary to tuple of dictionary values."""
    for arg in args:
        if type(args[arg]) == dict:
            args[arg] = tuple(args[arg].values())
    return args
