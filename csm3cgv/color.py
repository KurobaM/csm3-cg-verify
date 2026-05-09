from __future__ import annotations
from enum import Enum

import numpy as np
from numpy.typing import NDArray
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPixmap, QPainter, QColor


def rgb_to_xyz(r: float, g: float, b: float) -> NDArray[np.float64]:
    rv, gv, bv = (
        v / 12.92
        if v <= 0.04045
        else ((v + 0.055)/1.055) ** 2.4
        for v in (r, g, b)
    )
    t_m = np.array([
        [0.412348487282463, 0.357601378848728, 0.180450133868809],
        [0.212617188755020, 0.715202757697456, 0.072180053547523],
        [0.019328835341365, 0.119200459616243, 0.950370705042392]])
    xyz = np.matmul(t_m, np.array([rv, gv, bv]))
    xyz[xyz < 0] = 0.0
    return xyz


def f_t(t: float) -> float:
    if t > (6/29)**3:
        return t ** (1/3)
    else:
        return t/3 * (6/29) ** (-2) + 4/29


ft = np.vectorize(f_t, [np.float64])


def rgb_to_lab(rgb32: int):
    xyz = rgb_to_xyz((rgb32 & 0xff) / 0xff,
                     ((rgb32 >> 8) & 0xff) / 0xff,
                     ((rgb32 >> 16) & 0xff) / 0xff)
    xyz_ref = np.array([0.9504, 1.0000, 1.0889])
    tx, ty, tz = ft(xyz / xyz_ref)
    L = 116 * ty - 16
    a = 500 * (tx - ty)
    b = 200 * (ty - tz)
    return np.array([L, a, b])


class Weight(Enum):
    GRAPHIC_ARTS = 1
    TEXTILES = 2


def cie94_diff(lab1, lab2,
               weight: Weight = Weight.GRAPHIC_ARTS):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    d_L = L1 - L2
    C1 = (a1 ** 2 + b1 ** 2) ** (1/2)
    C2 = (a2 ** 2 + b2 ** 2) ** (1/2)
    d_C = C1 - C2
    d_a = a1 - a2
    d_b = b1 - b2
    d_H_2 = d_a ** 2 + d_b ** 2 - d_C ** 2
    SL = kC = kH = 1
    k = {Weight.GRAPHIC_ARTS: {'L': 1, '1': 0.045, '2': 0.015},
         Weight.TEXTILES: {'L': 2, '1': 0.048, '2': 0.014}}[weight]
    SC = 1 + k['1'] * C1
    SH = 1 + k['2'] * C1
    d_E = ((d_L / (k['L'] * SL)) ** 2
           + (d_C / (kC * SC)) ** 2
           + d_H_2 / ((kH * SH) ** 2)) ** (1/2)
    return d_E


class ColorInfo:
    def __init__(self, id: int, rgb32: int) -> None:
        self.id = id
        self.value = rgb32
        self.d_E: float = -1.0
        self.ref = None
        color = QColor(*(x for x in int.to_bytes(rgb32, 4, 'little')))
        self.pm = QPixmap(48, 48)
        self.pm.fill(color)

    def set_ref_color(self, ref: ColorInfo):
        lab_ref = rgb_to_lab(ref.value)
        lab = rgb_to_lab(self.value)
        self.d_E = cie94_diff(lab, lab_ref)
        self.ref = ref
        pt = QPainter(self.pm)
        pt.fillRect(
            QRect(0, 0, 24, 48),
            QColor(*(x for x in int.to_bytes(ref.value, 4, 'little'))))
        pt.end()

    def __eq__(self, other) -> bool:
        if not isinstance(other, ColorInfo):
            return False
        return self.value == other.value

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: ColorInfo) -> bool:
        if self.d_E < 0:
            lab_ref = rgb_to_lab(0)
            lab = rgb_to_lab(self.value)
            d_E = cie94_diff(lab, lab_ref)
            if other.d_E < 0:
                lab_o = rgb_to_lab(other.value)
                d_E_o = cie94_diff(lab_o, lab_ref)
            else:
                d_E_o = other.d_E
            return d_E < d_E_o
        else:
            if other.d_E < 0:
                lab_ref = rgb_to_lab(0)
                lab_o = rgb_to_lab(other.value)
                d_E_o = cie94_diff(lab_o, lab_ref)
            else:
                d_E_o = other.d_E
            return self.d_E < d_E_o

    def __le__(self, other):
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other):
        return not self.__le__(other)

    def __ge__(self, other):
        return not self.__lt__(other)
