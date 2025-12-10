# Copyright (C) 2025, KurobaM
# SPDX-License-Identifier: GPL-3.0-or-later


import os
import subprocess


try:
    from .main_ui import Ui_Form
except ModuleNotFoundError:
    import subprocess
    ui_path = os.path.join(os.path.dirname(__file__), 'main.ui')
    py_path = os.path.join(os.path.dirname(__file__), 'main_ui.py')
    if not os.path.isfile(ui_path):
        raise ImportError()
    subprocess.run(['pyuic5', '-o', py_path, ui_path])
    from .main_ui import Ui_Form
