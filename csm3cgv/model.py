from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np
from PyQt5.QtCore import (
    QAbstractTableModel, Qt, pyqtSignal, QObject, QModelIndex)
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import QWidget, QTableView, QHeaderView

try:
    from .graphic import Palette
except ImportError:
    from graphic import Palette

Flag = Qt.ItemFlag
Role = Qt.ItemDataRole
COLOR_WIDTH = COLOR_HEIGHT = 16


class ColorTableModel(QAbstractTableModel):
    ColorDataRole = Role.UserRole + 1

    def __init__(self, palette: Palette | None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.palette = palette
        self.pixmaps = self._create_pixmaps()

    def _create_pixmaps(self) -> list[QPixmap] | None:
        if not self.palette:
            return None
        pixmaps: list[QPixmap] = []
        for color in self.palette.color:
            pixmap = QPixmap(COLOR_WIDTH, COLOR_HEIGHT)
            pixmap.fill(QColor(color & 0xff, (color >> 8) & 0xff,
                               (color >> 16) & 0xff, (color >> 24) & 0xff))
            pixmaps.append(pixmap)
        return pixmaps

    def update(self, palette: Palette | None = None):
        self.beginResetModel()
        if palette:
            self.palette = palette
        self.pixmaps = self._create_pixmaps()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not self.palette:
            return 0
        return ceil(len(self.palette.color) / 16)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not self.palette:
            return 0
        return 16

    def data(self, index: QModelIndex, role: int = 0) -> Any:
        if not self.palette or not self.pixmaps:
            return None
        col = index.column()
        row = index.row()
        if role == Role.DecorationRole:
            try:
                return self.pixmaps[row * 16 + col]
            except IndexError:
                return None
        elif role == Role.DisplayRole:
            return ""
        elif role == self.ColorDataRole:
            return (row * 16 + col, self.palette.color[row * 16 + col])
        else:
            return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = 0) -> Any:
        if role == Role.DisplayRole:
            return section
        return super().headerData(section, orientation, role)


class PaletteTable(QTableView):
    color_clicked = pyqtSignal(tuple)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clicked.connect(self.cell_clicked)
        self.apply_style()

    def apply_style(self):
        hh = self.horizontalHeader()
        hh.setMinimumSectionSize(COLOR_WIDTH)  # type: ignore
        hh.setDefaultSectionSize(COLOR_WIDTH + 2)  # type: ignore
        vh = self.verticalHeader()
        vh.setMinimumSectionSize(COLOR_HEIGHT)  # type: ignore
        vh.setDefaultSectionSize(COLOR_HEIGHT + 2)  # type: ignore

    def cell_clicked(self, index: QModelIndex):
        model = self.model()
        if not model:
            return
        color: tuple[int, int] | None = model.data(
            index, ColorTableModel.ColorDataRole)
        if color is not None:
            self.color_clicked.emit(color)


class CharDetailModel(QAbstractTableModel):
    DataRole = Role.UserRole + 1
    data_changed = pyqtSignal()

    def __init__(self, data: np.ndarray | None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.char = data
        if not self.char:
            self.h = self.w = 0
        else:
            self.h, self.w = self.char.shape

    def update(self, data: np.ndarray):
        self.beginResetModel()
        self.char = data
        self.h, self.w = self.char.shape
        self.endResetModel()

    def replace(self, values: list[tuple[int, int]]):
        if self.char is None:
            return
        self.beginResetModel()
        try:
            for k, v in values:
                self.char[self.char == np.uint8(k)] = np.uint8(v)
        except Exception:
            pass
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self.h

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self.w

    def data(self, index: QModelIndex, role: int = 0) -> Any:
        if self.char is None:
            return None
        col = index.column()
        row = index.row()
        try:
            if role == Role.DisplayRole or role == Role.EditRole:
                return str(self.char[row, col])
            elif role == CharDetailModel.DataRole:
                return int(self.char[row, col])
            else:
                return None
        except IndexError:
            return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = 0) -> Any:
        if role == Role.DisplayRole:
            return section
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return (Flag.ItemIsSelectable | Flag.ItemIsEnabled
                | Flag.ItemIsEditable)  # type: ignore

    def setData(self, index: QModelIndex, value: Any, role: int = 0) -> bool:
        if self.char is None:
            return False
        row = index.row()
        col = index.column()
        if role == Role.EditRole:
            try:
                self.char[row, col] = np.uint8(int(value))
                self.dataChanged.emit(
                    index, index, [Role.DisplayRole, Role.EditRole])
                self.data_changed.emit()
                return True
            except Exception:
                return False
        return False


class CharTable(QTableView):
    pal_id_selected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clicked.connect(self.cell_clicked)
        self.apply_style()

    def apply_style(self):
        hh = self.horizontalHeader()
        hh.setMinimumSectionSize(36)  # type: ignore
        hh.setDefaultSectionSize(36)  # type: ignore
        vh = self.verticalHeader()
        vh.setMinimumSectionSize(20)  # type: ignore
        vh.setDefaultSectionSize(20)  # type: ignore

    def cell_clicked(self, index: QModelIndex):
        model = self.model()
        if not model:
            return
        idx: int | None = model.data(index, CharDetailModel.DataRole)
        if idx is not None:
            self.pal_id_selected.emit(idx)
