# https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.interp1d.html

import numpy as np
from scipy import interpolate

import xlwings as xw


@xw.func
@xw.arg("x", np.array, ndim=1)
@xw.arg("y", np.array, ndim=1)
@xw.arg("xnew", np.array, ndim=1)
@xw.arg("fill_value")
@xw.ret(expand="table")
def linear_interpolation(x, y, xnew, fill_value=None):
    f = interpolate.interp1d(x, y, fill_value=fill_value)
    ynew = f(xnew)

    return np.expand_dims(ynew, axis=1)


@xw.func
@xw.arg("points", np.array, ndim=2)
@xw.arg("values", np.array, ndim=1)
@xw.arg("points_new", np.array, ndim=2)
@xw.ret(expand="table")
def nd_linear_interpolation(points, values, points_new):
    func = interpolate.LinearNDInterpolator(points, values)

    values_new = func(points_new)

    return np.expand_dims(values_new, axis=1)


@xw.func
@xw.arg("values", np.array, ndim=2)
@xw.ret(expand="table")
def npravel(values):
    return np.expand_dims(np.ravel(values.T), axis=1)


@xw.func
@xw.arg("values", np.array, ndim=2)
@xw.arg("repeats")
@xw.ret(expand="table")
def nprepeat(values, repeats):
    return np.expand_dims(np.repeat(values, repeats), axis=1)
