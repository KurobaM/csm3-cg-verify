# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import json
import os
import traceback

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent, QImage, QKeyEvent
from PyQt5.QtWidgets import (QWidget, QFileDialog)


try:
    from .graphic import (Palette, BMP, CG4Header, SC4Header,
                          BGLayer, to_color16, to_color32)
    from .main_ui import Ui_Form
    from .model import ColorTableModel, CharDetailModel
except ImportError:
    from graphic import (Palette, BMP, CG4Header, SC4Header,
                         BGLayer, to_color16, to_color32)
    from main_ui import Ui_Form
    from model import ColorTableModel, CharDetailModel


class MainWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # member
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.bg = BGLayer()
        self.palette_data = None
        self.cg4h = None
        self.sc4h = None
        self.bmp_o = None
        self.working_dir, self.orig_dir = self.load_config()
        self.zoom_factor = 1
        self.selected_char = None
        self.selected_color: tuple[int, int] | None = None
        self.pal_model = ColorTableModel(None)
        self.char_model = CharDetailModel(None)
        self.ui.tbl_pal.setModel(self.pal_model)
        self.ui.tbl_char.setModel(self.char_model)
        # ui
        self.ui_setup()
        # signal
        self.ui.replace.returnPressed.connect(self.char_pixel_replace)
        self.ui.apply_btn.clicked.connect(self.apply_char_change)
        self.ui.set_color.returnPressed.connect(self.change_color)
        self.ui.btn_save.clicked.connect(self.save_img)
        self.ui.tbl_pal.color_clicked.connect(self.color_selected)
        self.ui.tbl_char.pal_id_selected.connect(self.select_pal_id)
        self.ui.zoom.valueChanged.connect(self.set_zoom)
        self.ui.load_bmp.clicked.connect(self.load_bmp)
        self.ui.load_bmp_o.clicked.connect(self.load_bmp_o)
        self.ui.load_cg4.clicked.connect(self.load_cg4)
        self.ui.load_sc4.clicked.connect(self.load_sc4)
        self.ui.load_pal.clicked.connect(self.load_pal)
        self.ui.preview.clicked.connect(self.view_bmp)
        self.ui.verify.clicked.connect(self.verify)
        self.ui.auto_fix_btn.clicked.connect(self.auto_fix)
        self.ui.export_err_img.clicked.connect(self.export_error_img)
        self.bg.pos_clicked.connect(self.show_coordinate_and_char)
        self.ui.copy.returnPressed.connect(self.copy_from_original)

    def ui_setup(self):
        self.ui.frame_orig_file.setVisible(False)
        self.ui.frame_pal.setVisible(False)
        self.ui.zoom.setMaximum(16)
        self.ui.zoom.setMinimum(1)
        self.ui.zoom.setValue(self.zoom_factor)
        self.ui.zoom.setSingleStep(1)
        self.ui.graphic_view.setScene(self.bg)
        self.ui.diff.setWordWrap(True)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # type: ignore
        self.save_config()
        return super().closeEvent(event)  # type: ignore

    def load_config(self):
        try:
            with open(os.path.join(os.path.dirname(__file__), 'config.json'),
                      'r', encoding='utf-8') as file:
                config = json.load(file)
                if (os.path.isdir(config['working_dir'])
                        and os.path.isdir(config['orig_dir'])):
                    return config['working_dir'], config['orig_dir']
                return None, None
        except Exception:
            return None, None

    def save_config(self):
        if self.working_dir is None:
            return
        try:
            config = dict()
            config['working_dir'] = self.working_dir
            config['orig_dir'] = self.orig_dir
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

    def save_img(self):
        if self.bg.bmp is None:
            return
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save BMP', folder, 'BMP image (*.bmp)')
            self.bg.bmp.save(path)
            self.ui.result.setText('Image saved successfully')
        except Exception:
            self.ui.result.setText(traceback.format_exc())

    def show_coordinate_and_char(self, pos: tuple[int, int]):
        self.ui.point.setText(f'X={pos[0]}, Y={pos[1]}')
        if not self.bg.bmp:
            return
        h, w = self.bg.bmp.pixels.shape
        if pos[0] < w and pos[1] < h:
            y = pos[1] // 8 * 8
            x = pos[0] // 8 * 8
            char = self.bg.bmp.pixels[y:y+8, x:x+8]
            self.selected_char = (x, y)
            self.char_model.update(char)
            self.ui.label_char.setText(
                f'Selected character: {x // 8 + y // 8 * w // 8}')
            self.ui.label_char_pm.setPixmap(
                self.bg.bmp.generate_char_pixmap(x, y, 6))

    def copy_from_original(self):
        if not self.bg.bmp or not self.bmp_o:
            return
        try:
            char = []
            s_char = [x.strip()
                      for x in self.ui.copy.text().split(',') if x.strip()]
            for v in s_char:
                if '-' in v:
                    s_start, s_end = [x.strip() for x in v.split('-')]
                    char.extend([x for x in range(int(s_start), int(s_end)+1)])
                else:
                    char.append(int(v))

            h, w = self.bmp_o.pixels.shape
            char_max = h // 8 * w // 8 - 1
            for c in char:
                if c > char_max:
                    continue
                y = c // (w // 8) * 8
                x = c % (w // 8) * 8
                pixels = self.bmp_o.pixels[y:y+8, x:x+8]
                self.bg.bmp.pixels[y:y+8, x:x+8] = pixels

            self.bg.bmp.img = None
            self.bg.bmp.error_img = None
            self.bg.bmp.charset = None
            self.bg.bmp.error = None
            self.view_bmp()
            self.verify()
        except Exception:
            print(traceback.format_exc())

    def char_pixel_replace(self):
        if self.char_model.char is None or self.bg.bmp is None:
            return
        try:
            s_pair = [x.strip().split('=')
                      for x in self.ui.replace.text().split(',') if x.strip()]
            values = []
            for x in s_pair:
                k = x[0].strip()
                v = x[1].strip()
                if not k or not v:
                    continue
                try:
                    values.append((int(k), int(v)))
                except ValueError:
                    pass
            if self.ui.checkBox.isChecked():
                for k, v in values:
                    try:
                        self.bg.bmp.pixels[
                            self.bg.bmp.pixels == np.uint8(k)] = np.uint8(v)
                    except Exception:
                        pass
            else:
                self.char_model.replace(values)
        except Exception:
            pass

    def apply_char_change(self):
        char = self.char_model.char
        if char is None or not self.bg.bmp or not self.selected_char:
            return
        x, y = self.selected_char
        self.bg.bmp.pixels[y: y+8, x: x+8] = char
        self.bg.bmp.img = None
        self.bg.bmp.error_img = None
        self.bg.bmp.charset = None
        self.bg.bmp.error = None
        self.view_bmp()
        self.verify()

    def change_color(self):
        if not self.selected_color:
            return
        if not self.bg.bmp or not self.bg.bmp.palette:
            return
        try:
            r, g, b = (int(s.strip()) & 0xff
                       for s in self.ui.set_color.text().split(','))
            index = self.selected_color[0]
            self.bg.bmp.palette.color[index] = np.uint32(
                r | g << 8 | b << 16 | 0xff << 24)
            self.bg.bmp.img = None
            self.view_bmp()
        except Exception:
            pass

    def select_pal_id(self, value: int):
        if not self.bg.bmp or not self.bg.bmp.palette:
            return
        self.color_selected((value, self.bg.bmp.palette.color[value]))

    def color_selected(self, value: tuple[int, int]):
        if not self.bg.bmp or not self.bg.bmp.palette:
            return
        self.selected_color = value

        lsb = self.ui.spin_lsb.value()
        if lsb == 0:
            map = self.bg.bmp.palette.color_map
            idx = value[1]
        else:
            map: dict[int, set[int]] = dict()
            mask_5b = ((0x1f - (1 << lsb) + 1)
                       | (0x1f - (1 << lsb) + 1) << 5
                       | (0x1f - (1 << lsb) + 1) << 10)
            idx = to_color16(value[1]) & mask_5b
            map: dict[int, set[int]] = dict()
            for k, v in self.bg.bmp.palette.color_map.items():
                k_shift = to_color16(k) & mask_5b
                if k_shift not in map:
                    map[k_shift] = set()
                map[k_shift].update(v)

        r, g, b, _ = (x for x in int.to_bytes(int(value[1]), 4, 'little'))
        r5 = round(r * 0x1f / 0xff)
        g5 = round(g * 0x1f / 0xff)
        b5 = round(b * 0x1f / 0xff)
        similar = sorted(list(map[idx]))
        similar = [similar[x: x + 10] for x in range(0, len(similar), 10)]
        lines = []
        for line in similar:
            lines.append(', '.join([str(x) for x in line]) + ',')
        similar_s = '{'+'\n         '.join(lines) + '}'

        self.ui.label_color.setText(
            f'Selected color: idx={value[0]}, '
            f'R={r}({r5}), G={g}({g5}), B={b}({b5})\n'
            f'Similar: {similar_s}')

    def view_bmp(self):
        if self.bg.bmp is not None:
            try:
                self.bg.set_image()
                self.pal_model.update(self.bg.bmp.palette)
            except Exception:
                self.ui.result.setText(traceback.format_exc())

    def auto_fix(self):
        if self.bg.bmp is None:
            return
        self.bg.bmp.auto_fix()
        self.verify()

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
                'R: >16 colors, G: only have palette error, \n'
                'B: pixels of minor color palettes')
        else:
            self.ui.result.setText(f'Do not found any error')
        diff = ''
        try:
            p_e_used = len(self.bg.bmp.palette_used())
        except Exception:
            p_e_used = 'ERROR'
        try:
            c_e = self.bg.bmp.char_count()
        except Exception:
            c_e = 'ERROR'

        if self.cg4h is not None:
            diff += (f'Palette: original -> {self.cg4h.color_count // 16} used'
                     f', edited -> {p_e_used} used\n'
                     f'Character: original -> {self.cg4h.char_count} chars'
                     f', edited -> {c_e} chars\n')
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
            self.working_dir = os.path.dirname(path)
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

    def load_bmp_o(self):
        if self.working_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.working_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open BMP', folder, 'Image (*.bmp)')
        if not os.path.isfile(path):
            return
        try:
            self.working_dir = os.path.dirname(path)
            self.bmp_o = BMP(path)
        except Exception as e:
            self.ui.bmp.setText(str(e))
        else:
            self.ui.bmp_o.setText(path)

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
        if self.orig_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.orig_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open CG4', folder, 'All (*)')
        if not os.path.isfile(path):
            return
        try:
            self.orig_dir = os.path.dirname(path)
            with open(path, 'rb') as f:
                data = f.read()
            self.cg4h = CG4Header(data)
            self.ui.cg4.setText(path)
        except Exception as e:
            self.ui.cg4.setText(str(e))

    def load_sc4(self):
        if self.orig_dir is None:
            folder = os.path.dirname(__file__)
        else:
            folder = self.orig_dir
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open SC4', folder, 'All (*)')
        if not os.path.isfile(path):
            return
        try:
            self.orig_dir = os.path.dirname(path)
            with open(path, 'rb') as f:
                data = f.read()
            self.sc4h = SC4Header(data)
            self.ui.sc4.setText(path)
        except Exception as e:
            self.ui.sc4.setText(str(e))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore
        if event.key() == Qt.Key.Key_F4:
            self.char_pixel_replace()
            self.apply_char_change()
            return event.accept()
        return super().keyPressEvent(event)
