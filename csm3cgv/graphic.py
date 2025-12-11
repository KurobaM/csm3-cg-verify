# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import numpy as np
from PIL import Image
from PyQt5.QtGui import QImage, QPixmap


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
        self.unk1 = data[0x18: 0x20]


class Palette:
    def __init__(self, color_8bpp: list[int], channel_separated=True):
        if channel_separated:
            self.color = np.array(self._to_color32(color_8bpp), np.uint32)
        else:
            self.color = np.array(color_8bpp, np.uint32)

    def _to_color32(self, data: list[int]):
        colors = [data[i:i+3] for i in range(0, len(data), 3)]
        return [(0xff << 24)
                + sum([(x[i] & 0xff) << (8 * i) for i in range(0, 3)])
                for x in colors]

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


class BMP:
    def __init__(self, path: str, palette: Palette | None = None) -> None:
        self._img = Image.open(path)
        if self._img.format != 'BMP':
            raise ValueError(f'Format not supported: {self._img.format}')
        self.width = self._img.width
        self.height = self._img.height
        if self._img.mode == 'P':
            self.pixels = np.array(self._img.getdata()
                                   ).reshape((self.height, self.width))
            pal = self._img.getpalette()
            if pal is None:
                self.palette = palette
            else:
                self.palette = Palette(pal)
        else:
            raise NotImplementedError(
                f'Bitmap mode not supported: {self._img.mode}')
        self.charset = None
        self.img = None
        self.error = None
        self.error_img = None

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
        self.charset = set()
        for y in range(0, self.height, 8):
            for x in range(0, self.width, 8):
                self.charset.add(
                    tuple(self.pixels[y:y+8, x:x+8].flatten().tolist())
                )
        return len(self.charset)

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

    def generate_palette_bmp(self):
        if self.img is None:
            self.img = self.create_image()
        pal_img = np.copy(self.img)
        print(pal_img)
        for y in range(0, self.height, 8):
            for x in range(0, self.width, 8):
                tile = self.pixels[y:y+8, x:x+8]
                colors = np.unique(tile)
                if len(colors) > 16:
                    raise ValueError('Tile has >16 colors at' + str(x) + ", " + str(y))
                print(colors)
                for xi in range(8):
                    for yi in range(8):
                        c = colors[0]
                        if len(colors) > (xi//2) + ((yi//2)*2):
                            c = colors[(xi//2) + ((yi//2)*2)]
                        pal_img[y+yi,x+xi] = self.palette.color[c]
                # for xi in range(4):
                #     for yi in range(4):
                #         c = colors[0]
                #         if xi+4*yi < len(colors):
                #             c = colors[xi+4*yi]
                #         pal_img[y+yi*2:y+yi*2+1, x+xi*2:x+xi*2+1] = c

        output_pixels = pal_img
        return output_pixels


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

    def draw_error(self, img: np.ndarray):
        if self.error is None:
            self.error = self.generate_error_map()
        red = 0xff0000ff
        green = 0xff00ff00
        blue = 0xffff0000
        print(img)
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
