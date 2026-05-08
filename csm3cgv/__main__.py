# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

from PyQt5.QtWidgets import QApplication

try:
    from .graphic import Palette, BMP, CG4Header, SC4Header
    from .main_form import MainWindow
except ImportError:
    from graphic import Palette, BMP, CG4Header, SC4Header
    from main_form import MainWindow


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
