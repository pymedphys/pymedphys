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

# Adapted from https://github.com/jrkerns/pylinac/tree/698254258ff4cb87812840c42b34c93ae32a4693

# pylint: disable = no-else-return

"""Module for classes that represent common geometric objects or patterns."""
import math
from itertools import zip_longest
from typing import Iterable, List, Optional, Tuple, Union

from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np

from .utilities import is_iterable


def tan(degrees) -> float:
    """Calculate the tangent of the given degrees."""
    return math.tan(math.radians(degrees))


def cos(degrees) -> float:
    """Calculate the cosine of the given degrees."""
    return math.cos(math.radians(degrees))


def sin(degrees) -> float:
    """Calculate the sine of the given degrees."""
    return math.sin(math.radians(degrees))


class Point:
    """A geometric point with x, y, and z coordinates/attributes."""

    z: Union[int, float]
    y: Union[int, float]
    x: Union[int, float]
    _attr_list: List[str] = ["x", "y", "z", "idx", "value"]
    _coord_list: List[str] = ["x", "y", "z"]

    def __init__(
        self, x=0, y=0, z=0, idx: Optional[int] = None, value=None, as_int: bool = False
    ):
        """
        Parameters
        ----------
        x : number-like, Point, iterable
            x-coordinate or iterable type containing all coordinates. If iterable, values are assumed to be in order: (x,y,z).
        y : number-like, optional
            y-coordinate
        idx : int, optional
            Index of point. Useful for sequential coordinates; e.g. a point on a circle profile is sometimes easier to describe
            in terms of its index rather than x,y coords.
        value : number-like, optional
            value at point location (e.g. pixel value of an image)
        as_int : boolean
            If True, coordinates are converted to integers.
        """
        if isinstance(x, Point):
            for attr in self._attr_list:
                item = getattr(x, attr, None)
                setattr(self, attr, item)
        elif is_iterable(x):
            for attr, item in zip_longest(
                self._attr_list, x, fillvalue=0  # type: ignore
            ):
                setattr(self, attr, item)
        else:
            self.x = x
            self.y = y
            self.z = z
            self.idx = idx
            self.value = value

        if as_int:
            self.x = int(round(self.x))
            self.y = int(round(self.y))
            self.z = int(round(self.z))

    def distance_to(self, thing: Union["Point", "Circle"]):
        """Calculate the distance to the given point.

        Parameters
        ----------
        thing : Circle, Point, 2 element iterable
            The other thing to calculate distance to.
        """
        if isinstance(thing, Circle):
            return abs(
                np.sqrt((self.x - thing.center.x) ** 2 + (self.y - thing.center.y) ** 2)
                - thing.radius
            )
        p = Point(thing)
        return math.sqrt(
            (self.x - p.x) ** 2 + (self.y - p.y) ** 2 + (self.z - p.z) ** 2
        )

    def as_array(self, only_coords: bool = True):
        """Return the point as a numpy array."""
        if only_coords:
            return np.array([getattr(self, item) for item in self._coord_list])
        else:
            return np.array(
                [
                    getattr(self, item)
                    for item in self._attr_list
                    if (getattr(self, item) is not None)
                ]
            )

    def __repr__(self):
        return f"Point(x={self.x:3.2f}, y={self.y:3.2f}, z={self.z:3.2f})"

    def __eq__(self, other):
        # if all attrs equal, points considered equal
        return all(
            getattr(self, attr) == getattr(other, attr) for attr in self._attr_list
        )

    def __sub__(self, other):
        p = Point()
        for attr in self._attr_list:
            try:
                diff = getattr(self, attr) - getattr(other, attr)
            except TypeError:
                diff = None
            setattr(p, attr, diff)
        return p

    def __mul__(self, other):
        for attr in self._attr_list:
            try:
                self.__dict__[attr] *= other
            except TypeError:
                pass

    def __truediv__(self, other):
        for attr in self._attr_list:
            val = getattr(self, attr)
            try:
                setattr(self, attr, val / other)
            except TypeError:
                pass
        return self


class Circle:
    """A geometric circle with center Point, radius, and diameter."""

    center: Point
    radius: float

    def __init__(
        self, center_point: Union[Point, Iterable] = (0, 0), radius: float = 0
    ):
        """
        Parameters
        ----------
        center_point : Point, optional
            Center point of the wobble circle.
        radius : float, optional
            Radius of the wobble circle.
        """
        if center_point is None:
            center_point = Point()
        elif isinstance(center_point, Point) or is_iterable(center_point):
            center_point = Point(center_point)
        else:
            raise TypeError("Circle center must be of type Point or iterable")

        self.center = center_point
        self.radius = radius

    @property
    def diameter(self) -> float:
        """Get the diameter of the circle."""
        return self.radius * 2

    def plot2axes(self, axes, edgecolor: str = "black", fill: bool = False):
        """Plot the Circle on the axes.

        Parameters
        ----------
        axes : matplotlib.axes.Axes
            An MPL axes to plot to.
        edgecolor : str
            The color of the circle.
        fill : bool
            Whether to fill the circle with color or leave hollow.
        """
        axes.add_patch(
            matplotlib.patches.Circle(
                (self.center.x, self.center.y),
                edgecolor=edgecolor,
                radius=self.radius,
                fill=fill,
            )
        )


class Vector:
    """A vector with x, y, and z coordinates."""

    def __init__(self, x=0, y=0, z=0):
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self):
        return f"Vector(x={self.x:.2f}, y={self.y:.2f}, z={self.z:.2f})"

    def as_scalar(self) -> float:
        """Return the scalar equivalent of the vector."""
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def distance_to(self, thing: Union[Circle, Point]):
        """Calculate the distance to the given point.

        Parameters
        ----------
        thing : Circle, Point, 2 element iterable
            The other point to calculate distance to.
        """
        if isinstance(thing, Circle):
            return abs(
                np.sqrt((self.x - thing.center.x) ** 2 + (self.y - thing.center.y) ** 2)
                - thing.radius
            )
        else:
            p = Point(thing)
            return math.sqrt(
                (self.x - p.x) ** 2 + (self.y - p.y) ** 2 + (self.z - p.z) ** 2
            )

    def __sub__(self, other):
        new_x = self.x - other.x
        new_y = self.y - other.y
        new_z = self.z - other.z
        return Vector(x=new_x, y=new_y, z=new_z)

    def __add__(self, other):
        new_x = self.x + other.x
        new_y = self.y + other.y
        new_z = self.z + other.z
        return Vector(x=new_x, y=new_y, z=new_z)


def vector_is_close(vector1: Vector, vector2: Vector, delta: float = 0.1) -> bool:
    """Determine if two vectors are with delta of each other; this is a simple coordinate comparison check."""
    for attr in ("x", "y", "z"):
        if np.isnan(getattr(vector1, attr)) and np.isnan(getattr(vector2, attr)):
            continue
        if (
            not getattr(vector2, attr) + delta
            >= getattr(vector1, attr)
            >= getattr(vector2, attr) - delta
        ):
            return False
    return True


class Line:
    """A line that is represented by two points or by m*x+b.

    Notes
    -----
    Calculations of slope, etc are from here:
    http://en.wikipedia.org/wiki/Linear_equation
    and here:
    http://www.mathsisfun.com/algebra/line-equation-2points.html
    """

    point1: Point
    point2: Point

    def __init__(self, point1: Point, point2: Point):
        """
        Parameters
        ----------
        point1 : Point
            One point of the line
        point2 : Point
            Second point along the line.
        """
        self.point1 = Point(point1)
        self.point2 = Point(point2)

    def __repr__(self):
        return (
            f"Line: p1:(x={self.point1.x:.1f}, y={self.point1.y:.1f}, z={self.point1.z:.1f}), "
            f"p2:(x={self.point2.x:.1f}, y={self.point2.y:.1f}, z={self.point2.z:.1f})"
        )

    @property
    def m(self) -> float:
        """Return the slope of the line.

        m = (y1 - y2)/(x1 - x2)

        From: http://www.purplemath.com/modules/slope.htm
        """
        return (self.point1.y - self.point2.y) / (self.point1.x - self.point2.x)

    @property
    def b(self) -> float:
        """Return the y-intercept of the line.

        b = y - m*x
        """
        return self.point1.y - (self.m * self.point1.x)

    def y(self, x):
        """Return y-value along line at position x."""
        return self.m * x + self.b

    def x(self, y):
        """Return x-value along line at position y."""
        return (y - self.b) / self.m

    @property
    def center(self) -> Point:
        """Return the center of the line as a Point."""
        mid_x = np.abs((self.point2.x - self.point1.x) / 2 + self.point1.x)
        mid_y = (self.point2.y - self.point1.y) / 2 + self.point1.y
        return Point(mid_x, mid_y)

    @property
    def length(self):
        """Return length of the line, if finite."""
        return self.point1.distance_to(self.point2)

    def distance_to(self, point):
        """Calculate the minimum distance from the line to a point.

        Equations are from here: http://mathworld.wolfram.com/Point-LineDistance2-Dimensional.html #14

        Parameters
        ----------
        point : Point, iterable
            The point to calculate distance to.
        """
        point = Point(point).as_array()
        lp1 = self.point1.as_array()
        lp2 = self.point2.as_array()
        numerator = np.sqrt(np.sum(np.power(np.cross((lp2 - lp1), (lp1 - point)), 2)))
        denominator = np.sqrt(np.sum(np.power(lp2 - lp1, 2)))
        return numerator / denominator

    def plot2axes(self, axes, width=1, color: str = "w"):
        """Plot the line to an axes.

        Parameters
        ----------
        axes : matplotlib.axes.Axes
            An MPL axes to plot to.
        color : str
            The color of the line.
        """
        axes.plot(
            (self.point1.x, self.point2.x),
            (self.point1.y, self.point2.y),
            linewidth=width,
            color=color,
        )


class Rectangle:
    """A rectangle with width, height, center Point, top-left corner Point, and bottom-left corner Point."""

    width: Union[int, float]
    height: Union[int, float]
    _as_int: bool
    center: Point

    def __init__(
        self,
        width: float,
        height: float,
        center: Union[Point, Tuple],
        as_int: bool = False,
    ):
        """
        Parameters
        ----------
        width : number
            Width of the rectangle.
        height : number
            Height of the rectangle.
        center : Point, iterable, optional
            Center point of rectangle.
        as_int : bool
            If False (default), inputs are left as-is. If True, all inputs are converted to integers.
        """
        if as_int:
            self.width = int(np.round(width))
            self.height = int(np.round(height))
        else:
            self.width = width
            self.height = height
        self._as_int = as_int
        self.center = Point(center, as_int=as_int)

    @property
    def br_corner(self) -> Point:
        """The location of the bottom right corner."""
        return Point(
            self.center.x + self.width / 2,
            self.center.y - self.height / 2,
            as_int=self._as_int,
        )

    @property
    def bl_corner(self) -> Point:
        """The location of the bottom left corner."""
        return Point(
            self.center.x - self.width / 2,
            self.center.y - self.height / 2,
            as_int=self._as_int,
        )

    @property
    def tl_corner(self) -> Point:
        """The location of the top left corner."""
        return Point(
            self.center.x - self.width / 2,
            self.center.y + self.height / 2,
            as_int=self._as_int,
        )

    @property
    def tr_corner(self) -> Point:
        """The location of the top right corner."""
        return Point(
            self.center.x + self.width / 2,
            self.center.y + self.height / 2,
            as_int=self._as_int,
        )

    def plot2axes(
        self,
        axes,
        edgecolor: str = "black",
        angle: float = 0.0,
        fill: bool = False,
        alpha: float = 1,
        facecolor: str = "g",
    ):
        """Plot the Rectangle to the axes.

        Parameters
        ----------
        axes : matplotlib.axes.Axes
            An MPL axes to plot to.
        edgecolor : str
            The color of the circle.
        angle : float
            Angle of the rectangle.
        fill : bool
            Whether to fill the rectangle with color or leave hollow.
        """
        axes.add_patch(
            matplotlib.patches.Rectangle(
                (self.bl_corner.x, self.bl_corner.y),
                width=self.width,
                height=self.height,
                angle=angle,
                edgecolor=edgecolor,
                alpha=alpha,
                facecolor=facecolor,
                fill=fill,
            )
        )
