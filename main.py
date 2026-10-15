#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin entry for the verifyfw framework (also the PyInstaller target).

    python main.py run <projdir> --target NAME=COM ... --mode {0,1}
    python main.py selftest <projdir>
"""

import sys

from verifyfw.cli import main

if __name__ == "__main__":
    sys.exit(main())
