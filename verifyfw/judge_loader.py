# -*- coding: utf-8 -*-
"""Project judge script loading.

Loads <proj>/judges.py so verify_items.json judge.fn references can be
resolved. Uses importlib by file path (mirrors the proven Phase 0 PoC) so it
works both from source and inside a PyInstaller exe.
"""

import importlib.util
from pathlib import Path


def load_judges(proj_dir):
    """Return the judges module; raises ValueError when missing or broken."""
    py = Path(proj_dir) / "judges.py"
    if not py.is_file():
        raise ValueError("judges.py not found: %s (a project directory must "
                         "contain it)" % py)
    modname = "verifyfw_project_judges"
    spec = importlib.util.spec_from_file_location(modname, py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def resolve_judges(judges_module, items):
    """Check every judge.fn reference resolves; returns {fn: callable}.

    Raises ValueError with the item/step location on the first unknown fn.
    """
    resolved = {}
    for it in items:
        for idx, step in enumerate(it["steps"], 1):
            judge = step.get("judge")
            if not judge:
                continue
            fn_name = judge["fn"]
            if fn_name in resolved:
                continue
            fn = getattr(judges_module, fn_name, None)
            if not callable(fn):
                raise ValueError("item %s step %d: judges.py has no function "
                                 "%r" % (it["id"], idx, fn_name))
            resolved[fn_name] = fn
    return resolved
