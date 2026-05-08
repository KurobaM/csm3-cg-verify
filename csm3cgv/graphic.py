# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from enum import Enum
import hashlib

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsScene, QGraphicsSceneMouseEvent)
import numpy as np
from PIL import Image


def to_color32(value: int):
    r = round((value & 0x1f) * 0xff / 0x1f)
    g = round((value >> 5 & 0x1f) * 0xff / 0x1f)
    b = round((value >> 10 & 0x1f) * 0xff / 0x1f)
    a = 0xff
    return r | g << 8 | b << 16 | a << 24


def to_color16(value: int):
    r = round((value & 0xff) * 0x1f / 0xff)
    g = round((value >> 8 & 0xff) * 0x1f / 0xff)
    b = round((value >> 16 & 0xff) * 0x1f / 0xff)
    return r | g << 5 | b << 10


class CG4Header:
    def __init__(self, data: bytes):
        if len(data) < 0x30:
            raise ValueError('Invalid CG4 file')
        if data[:4] != b'CG4 ':
            raise ValueError('Invalid CG4 file')
        self.magic = data[: 0x10]
        self.unk_0 = data[0x10: 0x14]
        self.char_size = int.from_bytes(data[0x14: 0x18], 'little')
        self.palette_size = int.from_bytes(data[0x18: 0x1C], 'little')
        self.char_count = int.from_bytes(data[0x1c: 0x20], 'little')
        self.color_count = int.from_bytes(data[0x20: 0x24], 'little')
        self.char_data_offset = int.from_bytes(data[0x24: 0x28], 'little')
        self.palette_data_offset = int.from_bytes(data[0x28: 0x2C], 'little')
        self.unk_0 = data[0x2C: 0x30]


class SC4Header:
    def __init__(self, data: bytes):
        if len(data) < 0x20:
            raise ValueError('Invalid SC4 file')
        if data[:4] != b'SC4 ':
            raise ValueError('Invalid SC4 file')
        self.magic = data[: 0x10]
        self.unk0 = data[0x10: 0x14]
        self.width = int.from_bytes(data[0x14: 0x16], 'little')
        self.height = int.from_bytes(data[0x16: 0x18], 'little')
        self.size = data[0x18: 0x1a]
        self.unk1 = data[0x1a: 0x20]


class Palette:
    def __init__(self, color_8bpp: list[int], channel_separated=True):
        if channel_separated:
            self.color = np.array(self._to_color32(color_8bpp), np.uint32)
        else:
            self.color = np.array(color_8bpp, np.uint32)
        self.color_map = self.generate_color_map()

    def _to_color32(self, data: list[int]):
        colors = [data[i:i+3] for i in range(0, len(data), 3)]
        return [(0xff << 24)
                + sum([(x[i] & 0xff) << (8 * i) for i in range(0, 3)])
                for x in colors]

    def generate_color_map(self):
        map: dict[int, set[int]] = dict()
        for i, v in enumerate(self.color):
            color = int(v)
            if color not in map:
                map[color] = set()
            map[color].add(i)
        return map

    def to_PIL_palette(self):
        out: list[int] = []
        for color in self.color:
            r, g, b, _ = (x for x in int.to_bytes(int(color), 4, 'little'))
            out.extend([r, g, b])
        out.extend([0] * (768 - len(out)))
        return out

    @classmethod
    def from_pal_file(cls, data: bytes):
        colors = [int.from_bytes(x + b'\xff', 'little')
                  for x in [data[i:i+3] for i in range(0, len(data), 3)]]
        return cls(colors, False)


def zoom(data_2d, factor):
    scaling_matrix = np.ones((factor, factor))
    dtype = data_2d.dtype
    scaled_arr = np.kron(data_2d, scaling_matrix)
    return scaled_arr.astype(dtype)


class BGChar:
    def __init__(self, data: bytes, pal256: bool = False):
        if pal256:
            self.size = 0x40
        else:
            self.size = 0x20
        self.pal256 = pal256
        if len(data) != self.size:
            raise ValueError('Invalid data size')
        self.data_2d = np.array(self._parse(
            data), dtype=np.uint8).reshape(8, 8)
        self._palette: int = 0

    def _parse(self, data: bytes) -> list[int]:
        out: list[int] = []
        if not self.pal256:
            for x in data:
                out.append(x & 0xf)
                out.append(x >> 4)
        else:
            for x in data:
                out.append(x)
        return out

    @classmethod
    def from_PIL_list(cls, pixels: list[int], pal256: bool = False):
        if len(pixels) != 8 * 8:
            raise ValueError('Char must be 8x8 pixels')
        obj = cls.__new__(cls)
        obj.pal256 = pal256
        obj._palette = 0
        shift = False
        if pal256:
            obj.size = 0x40
        else:
            obj.size = 0x20
            for v in pixels:
                if v > 0xf:
                    shift = True
                    break
        data = np.array(pixels, dtype=np.uint8)
        if shift:
            pal_set: set[int] = set((data // 16).tolist())
            if len(pal_set) != 1:
                raise ValueError(
                    'Invalid 16 color character (more than 1 palette)')
            obj._palette = pal_set.pop()
            data = data - 16 * obj._palette
        obj.data_2d = data.reshape(8, 8)
        return obj

    @property
    def hflip(self):
        return np.flip(self.data_2d, axis=1)

    @property
    def vflip(self):
        return np.flip(self.data_2d, axis=0)

    @property
    def hvflip(self):
        return np.flip(self.data_2d, axis=(0, 1))

    def get_2d(self, flip: tuple[bool, bool]) -> np.ndarray:
        if not flip[0] and not flip[1]:
            return self.data_2d
        if flip[0] and not flip[1]:
            return self.hflip
        elif not flip[0] and flip[1]:
            return self.vflip
        else:
            return self.hvflip

    def to_bytes(self, flip: tuple[bool, bool]):
        data = self.get_2d(flip).flatten()
        if self.pal256:
            return data.tobytes()
        else:
            packed = (data[1::2] << 4) | (data[::2] & 0x0f)
            return packed.tobytes()

    def hash(self, flip: tuple[bool, bool]):
        return hashlib.sha256(self.to_bytes(flip)).hexdigest()


def reduce_color(uint32_color: int, lsb: int):
    if lsb == 0:
        return uint32_color
    else:
        mask = 0x1f - (1 << lsb) + 1
        r = round((uint32_color & 0xff) * 0x1f / 0xff) & mask
        g = round((uint32_color >> 8 & 0xff) * 0x1f / 0xff) & mask
        b = round((uint32_color >> 16 & 0xff) * 0x1f / 0xff) & mask
        color16 = r | g << 5 | b << 10
        return to_color32(color16)


reduce = np.vectorize(reduce_color, [np.uint32])


def get_used_color(char: np.ndarray, palette: Palette):
    pal_map = char // 16
    pal_id = np.unique(pal_map)
    used_color32 = dict()
    for x in pal_id:
        used_color32[x] = palette.color[np.unique(char[pal_map == x])]
    return used_color32


def get_palette(pal_id: int, palette: Palette):
    return palette.color[pal_id * 16: (pal_id + 1) * 16]


def calc_suitable_pal(char: np.ndarray, palette: Palette, lsb: int):
    pal_map = char // 16
    pal_id = np.unique(pal_map)
    if len(pal_id) == 1:
        return pal_id[0]
    used_color32 = dict()
    all_color32 = dict()
    if lsb == 0:
        for x in pal_id:
            used_color32[x] = palette.color[
                np.unique(char[pal_map == x])]
            all_color32[x] = palette.color[x*16: (x+1)*16]
    else:
        for x in pal_id:
            used_color32[x] = reduce(palette.color[
                np.unique(char[pal_map == x])], lsb)
            all_color32[x] = reduce(palette.color[x*16: (x+1)*16], lsb)
    new_id = None
    for id in pal_id:
        colors = all_color32[id]
        ok = True
        for used in used_color32.values():
            if not np.all(np.isin(used, colors)):
                ok = False
                break
        if ok:
            new_id = id
            break
    return new_id


class BMP:
    def __init__(self, path: str, palette: Palette | None = None) -> None:
        with Image.open(path) as img:
            if img.format != 'BMP':
                raise ValueError(f'Format not supported: {img.format}')
            self.width = img.width
            self.height = img.height
            if img.mode == 'P':
                self.pixels = np.array(img.getdata(), dtype=np.uint8
                                       ).reshape((self.height, self.width))
                pal = img.getpalette()
                if pal is None:
                    self.palette = palette
                else:
                    self.palette = Palette(pal)
            else:
                raise NotImplementedError(
                    f'Bitmap mode not supported: {img.mode}')
        self.charset: dict[str, tuple[BGChar, int, int]] | None = None
        self.img = None
        self.error = None
        self.error_img = None

    def save(self, path):
        if self.palette is None:
            raise ValueError()
        img = Image.fromarray(self.pixels).convert('P')
        img.putpalette(self.palette.to_PIL_palette())
        img.save(path, 'BMP')

    def set_palette(self, palette: Palette, override=False):
        if self.palette is not None:
            self.palette = palette
        if override:
            self.palette = palette

    def crop(self, width: int, height: int, x=0, y=0):
        if (
            0 < width <= self.width and 0 < height <= self.height
            and 0 <= x < self.width and 0 <= y < self.height
            and x + width <= self.width and y + height <= self.height
        ):
            self.pixels = np.copy(self.pixels[y:height, x:width])
            self.width = width
            self.height = height

    def unused_color(self):
        if self.palette is None:
            return ''
        used_color = tuple(np.unique(self.pixels).tolist())
        color_count = len(self.palette.color)
        prev = -1
        result = '['
        for color_id in range(1, color_count):
            if color_id not in used_color:
                if prev + 1 == color_id:
                    if result[-1] != '-':
                        result = result + '-'
                    if (color_id + 1 in used_color
                            or color_id + 1 == color_count):
                        result = result + f'{color_id}'
                else:
                    result = result + f'{color_id}'
                prev = color_id
            else:
                if result[-1] != ' ' and result[-1] != '[':
                    result = result + ', '
        result = result + ']\n'
        return result

    def palette_used(self):
        return np.unique((self.pixels // 16))

    def char_count(self):
        if self.charset is not None:
            return len(self.charset)
        self.charset = dict()
        chars: list[BGChar] = []
        for y in range(0, self.height, 8):
            for x in range(0, self.width, 8):
                chars.append(BGChar.from_PIL_list(
                    self.pixels[y:y+8, x:x+8].flatten().tolist()))
        for char in chars:
            n_hash = char.hash((False, False))
            h_hash = char.hash((True, False))
            v_hash = char.hash((False, True))
            hv_hash = char.hash((True, True))
            if n_hash in self.charset:
                continue
            elif h_hash in self.charset:
                continue
            elif v_hash in self.charset:
                continue
            elif hv_hash in self.charset:
                continue
            else:
                self.charset[n_hash] = (char, 0, 0)
                self.charset[h_hash] = (char, 1, 0)
                self.charset[v_hash] = (char, 0, 1)
                self.charset[hv_hash] = (char, 1, 1)

        return len(self.charset) // 4

    def check_color_count(self, char: np.ndarray) -> bool:
        return len(set(char.flatten().tolist())) > 16

    def check_palette(self, char: np.ndarray) -> list[tuple[int, int]]:
        error: list[tuple[int, int]] = []
        palette_map = char // 16
        pal_id, count = np.unique(palette_map, return_counts=True)
        err = len(pal_id) > 1
        if not err:
            return []
        major_id = pal_id[count == count.max()]
        if len(major_id) > 1:
            major_id = major_id[0]
        minor_id = pal_id[pal_id != major_id]
        row, col = np.where(np.isin(palette_map, minor_id))
        for x, y in zip(col, row):
            error.append((int(x), int(y)))
        return error

    def auto_fix(self):
        if self.palette is None:
            return
        for y in range(0, self.height, 8):
            for x in range(0, self.width, 8):
                char = self.pixels[y:y+8, x:x+8]
                lsb = 0
                new_id = calc_suitable_pal(char, self.palette, lsb)
                if new_id is None:
                    lsb = 1
                    new_id = calc_suitable_pal(char, self.palette, lsb)
                if new_id is None:
                    continue
                useds = get_used_color(char, self.palette)
                colors = reduce(get_palette(new_id, self.palette), lsb)
                for id in useds:
                    old_pal = reduce(get_palette(id, self.palette), lsb)
                    if id == new_id:
                        continue
                    for v in useds[id]:
                        c = reduce_color(v, lsb)
                        old_idx = np.where(old_pal == c)[0][0] + 16 * id
                        idx = np.where(colors == c)[0][0] + 16 * new_id
                        char[char == old_idx] = idx
                self.pixels[y:y+8, x:x+8] = char
        self.error = None
        self.error_img = None

    def generate_error_map(self):
        err: list[tuple[bool, tuple[int, int], list[tuple[int, int]]]] = []
        for y in range(0, self.height, 8):
            for x in range(0, self.width, 8):
                char = self.pixels[y:y+8, x:x+8]
                count_err = self.check_color_count(char)
                pal_err = self.check_palette(char)
                if count_err or pal_err:
                    err.append((count_err, (x, y), pal_err))
        return err

    def create_image(self):
        if self.palette is None:
            raise ValueError('No Palette')
        return self.palette.color[self.pixels]

    def generate_pixmap(self, zoom_factor: int):
        if self.img is None:
            self.img = self.create_image()
        zoomed = zoom(self.img, zoom_factor)
        img = QImage(zoomed.tobytes(), self.width * zoom_factor,
                     self.height * zoom_factor,
                     QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(img)

    def get_char(self, x: int, y: int):
        return self.pixels[y:y+8, x:x+8]

    def generate_char_pixmap(self, x: int, y: int, zoom_factor: int):
        if self.palette is None:
            raise ValueError('No Palette')
        img = self.palette.color[self.get_char(x, y)]
        zoomed = zoom(img, zoom_factor)
        qimg = QImage(zoomed.tobytes(), 8 * zoom_factor, 8 * zoom_factor,
                      QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    def draw_error(self, img: np.ndarray):
        if self.error is None:
            self.error = self.generate_error_map()
        red = 0xff0000ff
        green = 0xff00ff00
        blue = 0xffff0000
        for e in self.error:
            redraw = True
            major_color = red
            minor_color = blue
            if not e[0] and e[2]:
                major_color = green
            elif e[0] and e[2]:
                pass
            elif e[0] and not e[2]:
                pass
            else:
                redraw = False
            if not redraw:
                continue
            x, y = e[1]
            img[y:y+8, x:x+8] = major_color
            for dx, dy in e[2]:
                img[y+dy, x+dx] = minor_color

    def create_error_image(self):
        if self.img is None:
            self.img = self.create_image()
        error_img = np.copy(self.img)
        self.draw_error(error_img)
        return error_img

    def create_error_mask(self):
        mask = np.zeros((self.height, self.width), np.uint32)
        self.draw_error(mask)
        return mask

    def generate_error_pixmap(self, zoom_factor):
        if self.error_img is None:
            self.error_img = self.create_error_image()
        zoomed = zoom(self.error_img, zoom_factor)
        img = QImage(zoomed.tobytes(), self.width * zoom_factor,
                     self.height * zoom_factor,
                     QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(img)


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
        super().mousePressEvent(event)  # type: ignore
        if event is not None and self.bmp is not None:
            point = self.item.mapFromScene(event.scenePos())
            x = int(point.x()) // self.zoom_factor
            y = int(point.y()) // self.zoom_factor
            if 0 <= x < self.bmp.width and 0 <= y < self.bmp.height:
                self.pos_clicked.emit((x, y))
