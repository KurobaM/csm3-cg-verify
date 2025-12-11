# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from enum import Enum
import json
import os
import traceback

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QCloseEvent, QImage
from PyQt5.QtWidgets import (QWidget, QGraphicsScene, QGraphicsSceneMouseEvent,
                             QGraphicsPixmapItem, QFileDialog)

from .graphic import Palette, BMP, CG4Header, SC4Header
from .main_ui import Ui_Form


class Mode(Enum):
    INIT = 0
    IMG_VIEW = 1
    ERR_VIEW = 2


class BGLayer(QGraphicsScene):
    pos_clicked = pyqtSignal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item = QGraphicsPixmapItem()
        self.bmp = None
        self.mode = Mode.INIT
        self.addItem(self.item)
        self.zoom_factor = 1

    def set_bitmap(self, bmp: BMP):
        self.bmp = bmp

    def set_image(self):
        self.mode = Mode.IMG_VIEW
        if self.bmp is not None:
            self.item.setPixmap(self.bmp.generate_pixmap(self.zoom_factor))

    def set_error_image(self):
        self.mode = Mode.ERR_VIEW
        if self.bmp is not None:
            self.item.setPixmap(
                self.bmp.generate_error_pixmap(self.zoom_factor))

    def update_zoom(self, zoom_factor: int):
        self.zoom_factor = zoom_factor
        if self.mode is Mode.IMG_VIEW:
            self.set_image()
        elif self.mode is Mode.ERR_VIEW:
            self.set_error_image()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        super().mousePressEvent(event)
        if event is not None and self.bmp is not None:
            point = self.item.mapFromScene(event.scenePos())
            x = int(point.x()) // self.zoom_factor
            y = int(point.y()) // self.zoom_factor
            if 0 <= x <= self.bmp.width and 0 <= y <= self.bmp.height:
                self.pos_clicked.emit((x, y))


class MainWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.bg = BGLayer()
        self.ui = Ui_Form()
        self.palette_data = None
        self.cg4h = None
        self.sc4h = None
        self.working_dir = self.load_config()
        self.ui.setupUi(self)
        self.ui.frame_orig_file.setVisible(False)
        self.ui.frame_pal.setVisible(False)
        self.zoom_factor = 1
        self.ui.zoom.setMaximum(16)
        self.ui.zoom.setMinimum(1)
        self.ui.zoom.setValue(self.zoom_factor)
        self.ui.zoom.setSingleStep(1)
        self.ui.graphic_view.setScene(self.bg)
        self.ui.diff.setWordWrap(True)
        self.ui.zoom.valueChanged.connect(self.set_zoom)
        self.ui.load_bmp.clicked.connect(self.load_bmp)
        self.ui.load_cg4.clicked.connect(self.load_cg4)
        self.ui.load_sc4.clicked.connect(self.load_sc4)
        self.ui.load_pal.clicked.connect(self.load_pal)
        self.ui.preview.clicked.connect(self.view_bmp)
        self.ui.verify.clicked.connect(self.verify)
        self.ui.export_err_img.clicked.connect(self.export_error_img)
        self.ui.export_pal_img.clicked.connect(self.export_palette_img)
        self.bg.pos_clicked.connect(self.show_coordinate)

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        self.save_config()
        return super().closeEvent(a0)

    def load_config(self):
        try:
            with open(os.path.join(os.path.dirname(__file__), 'config.json'),
                      'r', encoding='utf-8') as file:
                config = json.load(file)
                if os.path.isdir(config['working_dir']):
                    return config['working_dir']
                return None
        except Exception:
            return None

    def save_config(self):
        if self.working_dir is None:
            return
        try:
            config = dict()
            config['working_dir'] = self.working_dir
            with open(os.path.join(os.path.dirname(__file__), 'config.json'),
                      'w', encoding='utf-8') as file:
                json.dump(config, file)
        except Exception:
            return

    def export_error_img(self):
        if self.bg.bmp is None:
            return
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        try:
            mask = self.bg.bmp.create_error_mask()
            img = QImage(mask.tobytes(), self.bg.bmp.width, self.bg.bmp.height,
                         QImage.Format.Format_RGBA8888)
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save PNG', folder, 'PNG image (*.png)')
            if img.save(path, 'PNG'):
                self.ui.result.setText('Mask file saved successfully')
            else:
                self.ui.result.setText('Failed to save mask file')
        except Exception:
            self.ui.result.setText(traceback.format_exc())

    def export_palette_img(self):
        if self.bg.bmp is None:
            return
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        try:
            mask = self.bg.bmp.generate_palette_bmp()
            img = QImage(mask.tobytes(), self.bg.bmp.width, self.bg.bmp.height,
                         QImage.Format.Format_RGBA8888)
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save PNG', folder, 'PNG image (*.png)')
            if img.save(path, 'PNG'):
                self.ui.result.setText('Palette file saved successfully')
            else:
                self.ui.result.setText('Failed to save palette file')
        except Exception:
            self.ui.result.setText(traceback.format_exc())


    def show_coordinate(self, pos: tuple[int, int]):
        self.ui.point.setText(f'X={pos[0]}, Y={pos[1]}')

    def view_bmp(self):
        if self.bg.bmp is not None:
            try:
                self.bg.set_image()
            except Exception:
                self.ui.result.setText(traceback.format_exc())

    def verify(self):
        if self.bg.bmp is None:
            return
        if not self.ui.orig_check.isChecked():
            self.cg4h = None
            self.sc4h = None
        if not self.ui.pal_check.isChecked():
            self.palette_data = None
        try:
            self.bg.set_error_image()
        except Exception:
            self.ui.result.setText(traceback.format_exc())
            return
        err = self.bg.bmp.error
        if err:
            self.ui.result.setText(
                f'Found {len(err)} character(s) with error.\n'
                'R: >16 colors, G: only have palette error, '
                'B: pixels of minor color palettes')
        else:
            self.ui.result.setText(f'Do not found any error')
        diff = ''
        if self.cg4h is not None:
            diff += (f'Palette: original -> {self.cg4h.color_count // 16} used'
                     f', edited -> {len(self.bg.bmp.palette_used())} used\n'
                     f'Character: original -> {self.cg4h.char_count} chars'
                     f', edited -> {self.bg.bmp.char_count()} chars\n')
        if self.sc4h is not None:
            diff += (
                f'Actual size: {self.sc4h.width}x{self.sc4h.height}\n')
        diff += f'Unused colors: {self.bg.bmp.unused_color()}'
        self.ui.diff.setText(diff)

    def set_zoom(self, value: int):
        self.zoom_factor = value
        try:
            self.bg.update_zoom(self.zoom_factor)
        except Exception:
            self.ui.result.setText(traceback.format_exc())

    def load_bmp(self):
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open BMP', folder, 'Image (*.bmp)')
        if not os.path.isfile(path):
            return
        try:
            if self.palette_data is not None:
                bmp = BMP(path, self.palette_data)
            else:
                bmp = BMP(path)
        except Exception as e:
            self.ui.bmp.setText(str(e))
        else:
            self.bg.set_bitmap(bmp)
            self.working_dir = os.path.dirname(path)
            self.ui.bmp.setText(path)
            self.ui.width.setText(str(bmp.width))
            self.ui.height.setText(str(bmp.height))

    def load_pal(self):
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open palette file', folder, 'Palette file (*.pal)')
        if not os.path.isfile(path):
            return
        try:
            with open(path, 'rb') as f:
                data = f.read()
            pal = Palette.from_pal_file(data)
            if self.bg.bmp is not None:
                self.bg.bmp.set_palette(pal, self.ui.override.isChecked())
            self.palette_data = pal
            self.ui.pal.setText(path)
        except Exception as e:
            self.ui.pal.setText(str(e))

    def load_cg4(self):
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open CG4', folder, 'All (*)')
        if not os.path.isfile(path):
            return
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.cg4h = CG4Header(data)
            self.ui.cg4.setText(path)
        except Exception as e:
            self.ui.cg4.setText(str(e))

    def load_sc4(self):
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open SC4', folder, 'All (*)')
        if not os.path.isfile(path):
            return
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.sc4h = SC4Header(data)
            self.ui.sc4.setText(path)
        except Exception as e:
            self.ui.sc4.setText(str(e))
