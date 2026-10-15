# -*- coding: utf-8 -*-
"""CLI entry: run / selftest subcommands.

    python main.py run [projdir] --target NAME=COM [--target ...] \
        [--mode {0,1}] [--max-rounds N] [--continue-on-fail] [--no-judge]
    python main.py selftest [projdir]

    --mode defaults to 0 (single round, stop on failure). In mode 1 a failed
    round stops the whole run unless --continue-on-fail is given (then the
    next round resets the board and retries).

    In a frozen exe `run` is the default subcommand and may be omitted:
        <app>.exe --target NAME=COM ... --mode {0,1}
    (the exe is purpose-built to run a project; `selftest` stays explicit)

Exit codes follow the production convention: 0 = all PASS, 1 = FAIL found,
2 = usage / config / serial environment error.
"""

import argparse
import copy
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import session as session_mod
from .config import load_project, load_verify_items
from .judge_loader import load_judges, resolve_judges
from .orchestrator import round_stats, run_round
from .reporter import Reporter
from .selftest import run_selftest
from .session import SerialSession, read_for_all

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ENV = 2

# Project used when no path is given: from source it resolves to
# projects/<BUNDLED_PROJECT> under the repo root; a purpose-built exe
# bundles that same directory (PyInstaller --add-data). Point it at your
# own project before packaging a dedicated exe.
BUNDLED_PROJECT = "_template"


def _parse_bindings(pairs):
    bindings = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError("--target must be NAME=COM, got %r" % p)
        name, com = p.split("=", 1)
        name, com = name.strip(), com.strip()
        if not name or not com:
            raise ValueError("--target must be NAME=COM, got %r" % p)
        if name in bindings:
            raise ValueError("--target %s given twice" % name)
        bindings[name] = com
    return bindings


def _resolve_coms(targets, bindings):
    """CLI bindings win over optional per-target com defaults (D2)."""
    unknown = sorted(set(bindings) - {t["name"] for t in targets})
    if unknown:
        raise ValueError("--target unknown name(s): %s (project defines: %s)"
                         % (unknown, ", ".join(t["name"] for t in targets)))
    coms = {}
    missing = []
    for t in targets:
        com = bindings.get(t["name"]) or t.get("com")
        if not com:
            missing.append(t["name"])
        else:
            coms[t["name"]] = com
    if missing:
        raise ValueError("--target missing for: %s (project defines: %s)"
                         % (missing, ", ".join(t["name"] for t in targets)))
    return coms


def _check_step_targets(proj, items):
    """Cross-check step.target against configured targets (fail-fast)."""
    names = {t["name"] for t in proj["targets"]}
    for it in items:
        for idx, step in enumerate(it["steps"], 1):
            if step.get("type") != "sleep" and step["target"] not in names:
                raise ValueError("item %s step %d: unknown target %r "
                                 "(project defines: %s)"
                                 % (it["id"], idx, step["target"],
                                    ", ".join(sorted(names))))


def _without_judges(items):
    """Return a deep copy with every judge field removed (bring-up mode)."""
    items = copy.deepcopy(items)
    for it in items:
        for step in it["steps"]:
            step.pop("judge", None)
    return items


def _resolve_project(project):
    """Default to the bundled project when no path is given.

    In a frozen exe the project is bundled under sys._MEIPASS; from source it
    resolves relative to this file (repo root/projects/<BUNDLED_PROJECT>).
    """
    if project:
        return project
    if getattr(sys, "_MEIPASS", None):
        return str(Path(sys._MEIPASS) / "projects" / BUNDLED_PROJECT)
    return str(Path(__file__).resolve().parent.parent / "projects"
               / BUNDLED_PROJECT)


def cmd_run(args):
    project = _resolve_project(args.project)
    try:
        proj = load_project(project)
        items = load_verify_items(project)
    except ValueError as e:
        print("[ENV] %s" % e)
        return EXIT_ENV
    if args.no_judge:
        items = _without_judges(items)
        print("[INFO] judging disabled (--no-judge): steps only fail on "
              "prompt timeout")
    if args.mode == "0" and (args.continue_on_fail or args.max_rounds):
        print("[INFO] --continue-on-fail/--max-rounds apply to mode 1 only; "
              "ignored (mode 0 runs a single round and stops on failure)")
    try:
        judges_mod = load_judges(project)
        judges = resolve_judges(judges_mod, items)
    except ValueError as e:
        print("[ENV] %s" % e)
        return EXIT_ENV
    try:
        _check_step_targets(proj, items)
    except ValueError as e:
        print("[ENV] %s" % e)
        return EXIT_ENV

    print("[INFO] %d item(s): %s"
          % (len(items), ", ".join("%d %s" % (i["id"], i["name"])
                                   for i in items)))

    try:
        coms = _resolve_coms(proj["targets"], _parse_bindings(args.target))
    except ValueError as e:
        print("[ENV] %s" % e)
        return EXIT_ENV

    if not session_mod.serial_available():
        print("[ENV] pyserial is required: pip install pyserial")
        return EXIT_ENV
    if args.max_rounds < 0:
        print("[ENV] --max-rounds must be >= 0")
        return EXIT_ENV

    run_dir = Path("logs") / ("run_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions = {}
    try:
        for t in proj["targets"]:
            name = t["name"]
            sessions[name] = SerialSession(name, t["prompt"], coms[name],
                                           t["serial"], run_dir / ("%s.log" % name))
            sessions[name].open()
            print("[INFO] %s opened on %s" % (name, coms[name]))
    except Exception as e:
        print("[ENV] failed to open serial port for target %s: %s"
              % (t["name"], e))
        for s in sessions.values():
            s.close()
        return EXIT_ENV

    reporter = Reporter(run_dir, args.mode, project)
    print("[INFO] run dir: %s" % run_dir)

    def sleep_all(seconds):
        read_for_all(sessions, seconds)

    any_fail = False
    try:
        if args.mode == "0":
            any_fail = not run_round(1, items, sessions, sleep_all, reporter,
                                     judges)
        else:
            round_no = 1
            while True:
                ok = run_round(round_no, items, sessions, sleep_all, reporter,
                               judges)
                if not ok:
                    any_fail = True
                    if not args.continue_on_fail:
                        # Default stop-on-fail: the next round's item 1 would
                        # reset the board and destroy the failure scene, so
                        # break here and keep the scene for inspection.
                        break
                    # Retry path: no separate reset step, item 1 of the next
                    # round performs reset + cold-boot wait + probing itself.
                if args.max_rounds and round_no >= args.max_rounds:
                    break
                round_no += 1
    except KeyboardInterrupt:
        print("\n[INFO] interrupted by user")
    except Exception:
        # Script/environment errors are not check FAILs: keep the stack,
        # exit 2 so CI distinguishes "DUT failed" from "harness broken".
        traceback.print_exc()
        return EXIT_ENV
    finally:
        for s in sessions.values():
            s.close()

    if args.mode == "1":
        total, passed, failed, streak = round_stats(reporter.meta["rounds"])
        print("[STAT] rounds=%d pass=%d fail=%d max_pass_streak=%d"
              % (total, passed, failed, streak))
    return EXIT_FAIL if any_fail else EXIT_OK


def cmd_selftest(args):
    project = _resolve_project(args.project)
    return run_selftest(project, load_project, load_verify_items,
                        load_judges, resolve_judges)


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Generic serial verification framework "
                    "(projects carry config + judges, framework stays "
                    "untouched)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="run a project against real targets")
    pr.add_argument("project", nargs="?",
                    help="project directory (default: bundled "
                         "projects/%s/)" % BUNDLED_PROJECT)
    pr.add_argument("--target", action="append", required=True,
                    metavar="NAME=COM", help="bind target NAME to serial port COM")
    pr.add_argument("--mode", choices=["0", "1"], default="0",
                    help="0: single round, stop on failure and keep the "
                         "failure scene (default); 1: loop rounds")
    pr.add_argument("--max-rounds", type=int, default=0, metavar="N",
                    help="mode 1 only: stop after N rounds and print statistics "
                         "(0 = loop forever until Ctrl+C)")
    pr.add_argument("--continue-on-fail", action="store_true",
                    help="mode 1 only: after a failed round start a reset "
                         "round instead of stopping; default stops on the "
                         "first failed round, keeping the failure scene")
    pr.add_argument("--no-judge", action="store_true",
                    help="bring-up mode: ignore all judge rules, steps only "
                         "fail on prompt timeout")
    pr.set_defaults(fn=cmd_run)

    ps = sub.add_parser("selftest", help="offline checks: config, items, sample echoes")
    ps.add_argument("project", nargs="?",
                    help="project directory (default: bundled "
                         "projects/%s/)" % BUNDLED_PROJECT)
    ps.set_defaults(fn=cmd_selftest)
    return p.parse_args(argv)


def main(argv=None):
    # Windows consoles may default to GBK; force UTF-8 so Chinese survives
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    # Frozen exe is purpose-built to run: make `run` the default subcommand.
    # From source the subcommand stays explicit (python main.py run ...).
    if getattr(sys, "frozen", False) and (not argv or argv[0] not in ("run", "selftest")):
        argv = ["run"] + argv
    args = parse_args(argv)
    return args.fn(args)
