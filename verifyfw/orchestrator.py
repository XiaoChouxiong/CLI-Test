# -*- coding: utf-8 -*-
"""Orchestrator: run verify items (JSON steps) against serial sessions.

Steps are executed linearly; the first FAIL aborts the item (mode 0/1
fail-fast semantics). Judge rules reference functions from the project
judges.py, resolved by judge_loader.resolve_judges.
"""

import time

from .helpers import strip_ansi
from .reporter import CheckOutcome, ItemResult, RoundResult


def _fmt_desc(step):
    if step.get("type") == "sleep":
        sec = step.get("seconds", 0)
        sec = int(sec) if float(sec).is_integer() else sec
        return "sleep %ss" % sec
    return "%s> %s" % (step.get("target", "?"), step.get("cmd", "") or "<CR>")


def run_item(item, sessions, sleep_all, judges):
    """Run all steps of one item; first failing step aborts the item.

    judges maps fn name -> callable with signature
    fn(text, args, ctx) -> (ok, detail, evidence).
    """
    t_start = time.monotonic()
    checks = []
    for idx, step in enumerate(item["steps"], 1):
        if step.get("type") == "sleep":
            sleep_all(float(step.get("seconds", 0)))
            checks.append(CheckOutcome(idx, _fmt_desc(step), True))
            continue
        sess = sessions[step["target"]]
        text, ok = sess.send_cmd(step.get("cmd", ""), step.get("timeout_s", 10))
        desc = _fmt_desc(step)
        if not ok:
            checks.append(CheckOutcome(idx, desc, False,
                                       "timeout, prompt not seen"))
            return ItemResult(item["id"], item["name"], False,
                              time.monotonic() - t_start, checks)
        judge = step.get("judge")
        if judge:
            fn = judges[judge["fn"]]
            passed, detail, evidence = fn(
                strip_ansi(text), judge.get("args", {}),
                {"target": step["target"], "prompt": sess.prompt})
            checks.append(CheckOutcome(idx, desc, bool(passed), detail,
                                       evidence or []))
            if not passed:
                return ItemResult(item["id"], item["name"], False,
                                  time.monotonic() - t_start, checks)
        else:
            checks.append(CheckOutcome(idx, desc, True))
    return ItemResult(item["id"], item["name"], True,
                      time.monotonic() - t_start, checks)


def run_round(round_no, items, sessions, sleep_all, reporter, judges):
    t0 = time.monotonic()
    rr = RoundResult(round_no=round_no, passed=True)
    for item in items:
        res = run_item(item, sessions, sleep_all, judges)
        rr.items.append(res)
        if not res.passed:
            rr.passed = False
            break   # mode-0 semantics: later items depend on earlier state
    rr.duration_s = time.monotonic() - t0
    reporter.round(rr)
    return rr.passed


def round_stats(rounds):
    """Mode 1 statistics, identical formula to the old script."""
    total = len(rounds)
    passed_rounds = sum(1 for r in rounds if r.passed)
    max_streak = cur = 0
    for r in rounds:
        cur = cur + 1 if r.passed else 0
        max_streak = max(max_streak, cur)
    return total, passed_rounds, total - passed_rounds, max_streak


__all__ = ["run_item", "run_round", "round_stats"]
