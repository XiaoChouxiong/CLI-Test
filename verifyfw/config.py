# -*- coding: utf-8 -*-
"""Project config loading and schema validation (v2, environment-only).

Schema (planning doc "项目配置 schema（仅环境段，v2）"):
    {
      "targets": [{"name": "...", "prompt": "...", "serial": {}, "com": "..."}],
      "serial": {"baudrate": ..., "bytesize": ..., "parity": "...", "stopbits": ...}
    }
verify_items / judges are NOT part of project.json (D9): the flow lives in
verify_items.json, pass criteria in the project judges.py. COM ports stay
out of the file (machine-specific, D2) except as an optional per-target
default.
"""

import json
from pathlib import Path

KNOWN_SERIAL_KEYS = {"baudrate", "bytesize", "parity", "stopbits"}
KNOWN_TARGET_KEYS = {"name", "prompt", "serial", "com"}
KNOWN_TOP_KEYS = {"targets", "serial"}


def _bad(msg):
    raise ValueError("project.json: %s" % msg)


def load_project(proj_dir):
    """Load + validate; returns {"targets": [...], "serial": {...},
    "project_dir": Path} with per-target serial merged over the top one."""
    pdir = Path(proj_dir)
    pfile = pdir / "project.json"
    if not pfile.is_file():
        _bad("not found: %s (a project directory must contain it)" % pfile)
    try:
        with open(pfile, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _bad("cannot load: %s" % e)
    if not isinstance(cfg, dict):
        _bad("top level must be an object")

    unknown = sorted(set(cfg) - KNOWN_TOP_KEYS)
    if unknown:
        _bad("unknown top-level key(s): %s (known: %s; verify items live "
             "in verify_items.json per D9)" % (unknown, sorted(KNOWN_TOP_KEYS)))

    targets = cfg.get("targets")
    if not isinstance(targets, list) or not targets:
        _bad("targets must be a non-empty list")
    names = []
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            _bad("targets[%d] must be an object" % i)
        unknown = sorted(set(t) - KNOWN_TARGET_KEYS)
        if unknown:
            _bad("targets[%d] unknown key(s): %s" % (i, unknown))
        name, prompt = t.get("name"), t.get("prompt")
        if not isinstance(name, str) or not name:
            _bad("targets[%d].name must be a non-empty string" % i)
        if not isinstance(prompt, str) or not prompt:
            _bad("targets[%d].prompt must be a non-empty string" % i)
        if "com" in t and (not isinstance(t["com"], str) or not t["com"]):
            _bad("targets[%d].com must be a non-empty string" % i)
        names.append(name)
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        _bad("duplicate target name(s): %s" % dup)

    serial = _validate_serial(cfg.get("serial", {}), "serial")
    merged = []
    for t in targets:
        eff = dict(serial)
        eff.update(_validate_serial(t.get("serial", {}),
                                     "targets[%s].serial" % t["name"]))
        merged.append({"name": t["name"], "prompt": t["prompt"],
                       "com": t.get("com"), "serial": eff})
    return {"targets": merged, "serial": serial, "project_dir": pdir}


def _validate_serial(sc, where):
    if not isinstance(sc, dict):
        _bad("%s must be an object" % where)
    unknown = sorted(set(sc) - KNOWN_SERIAL_KEYS)
    if unknown:
        _bad("%s unknown key(s): %s" % (where, unknown))
    out = {}
    if "baudrate" in sc:
        if not isinstance(sc["baudrate"], int) or sc["baudrate"] <= 0:
            _bad("%s.baudrate must be a positive int" % where)
        out["baudrate"] = sc["baudrate"]
    if "bytesize" in sc:
        if sc["bytesize"] not in (5, 6, 7, 8):
            _bad("%s.bytesize must be one of 5/6/7/8" % where)
        out["bytesize"] = sc["bytesize"]
    if "parity" in sc:
        if sc["parity"] not in ("N", "E", "O"):
            _bad("%s.parity must be N/E/O" % where)
        out["parity"] = sc["parity"]
    if "stopbits" in sc:
        if sc["stopbits"] not in (1, 2):
            _bad("%s.stopbits must be 1 or 2" % where)
        out["stopbits"] = sc["stopbits"]
    return out


KNOWN_ITEMS_KEYS = {"verify_items"}


def _bad_items(msg):
    raise ValueError("verify_items.json: %s" % msg)


def load_verify_items(proj_dir):
    """Load + validate verify_items.json; returns the verify item list.

    Each item: {"id": int, "name": str, "steps": [...]}. A step is either a
    command (target/cmd/timeout_s, optional judge) or a sleep
    (type="sleep", seconds>0). judge = {"fn": str, "args": {...}} references
    a function in the project judges.py (loaded separately).
    """
    pdir = Path(proj_dir)
    vfile = pdir / "verify_items.json"
    if not vfile.is_file():
        _bad_items("not found: %s" % vfile)
    try:
        with open(vfile, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _bad_items("cannot load: %s" % e)
    if not isinstance(cfg, dict):
        _bad_items("top level must be an object")
    unknown = sorted(set(cfg) - KNOWN_ITEMS_KEYS)
    if unknown:
        _bad_items("unknown top-level key(s): %s" % unknown)

    items = cfg.get("verify_items")
    if not isinstance(items, list) or not items:
        _bad_items("verify_items must be a non-empty list")
    ids = [it.get("id") for it in items]
    if any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
        _bad_items("verify item id must be int: %s" % ids)
    if len(set(ids)) != len(ids):
        _bad_items("duplicate verify item id: %s" % ids)

    for it in items:
        if not isinstance(it, dict):
            _bad_items("verify item must be an object")
        it_id = it.get("id")
        name = it.get("name")
        if not isinstance(name, str) or not name:
            _bad_items("item %r: name must be a non-empty string" % it_id)
        steps = it.get("steps")
        if not isinstance(steps, list) or not steps:
            _bad_items("item %r: steps must be a non-empty list" % it_id)
        for idx, step in enumerate(steps, 1):
            _validate_step(it_id, idx, step)
    return items


def _validate_step(it_id, idx, step):
    if not isinstance(step, dict):
        _bad_items("item %s step %d: must be an object" % (it_id, idx))
    if step.get("type") == "sleep":
        if not step.get("seconds", 0) > 0:
            _bad_items("item %s step %d: sleep needs seconds>0" % (it_id, idx))
        return
    target = step.get("target")
    if not isinstance(target, str) or not target:
        _bad_items("item %s step %d: target must be a non-empty string"
                   % (it_id, idx))
    cmd = step.get("cmd", "")
    if not isinstance(cmd, str):
        _bad_items("item %s step %d: cmd must be a string" % (it_id, idx))
    if not step.get("timeout_s", 0) > 0:
        _bad_items("item %s step %d: timeout_s must be >0" % (it_id, idx))
    judge = step.get("judge")
    if judge is None:
        return
    if not isinstance(judge, dict):
        _bad_items("item %s step %d: judge must be an object" % (it_id, idx))
    fn = judge.get("fn")
    if not isinstance(fn, str) or not fn:
        _bad_items("item %s step %d: judge.fn must be a non-empty string"
                   % (it_id, idx))
    args = judge.get("args")
    if args is not None and not isinstance(args, dict):
        _bad_items("item %s step %d: judge.args must be an object" % (it_id, idx))
