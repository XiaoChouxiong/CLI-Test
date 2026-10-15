# -*- coding: utf-8 -*-
"""Framework text utilities (ANSI stripping shared by the judge path)."""

import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text):
    """Remove ANSI color codes so text matching is reliable."""
    return ANSI_RE.sub("", text)
