# -*- coding: utf-8 -*-
"""Offline selftest: config schema + items + judges + replayed echo cases.

Semantics ported from the old --selftest: every judgment in the project is
exercised offline against sample echoes, PASS/FAIL per case, summary line,
exit 0 only when nothing failed. Samples live in the project
(<proj>/selftest_cases/*.json); each case replays canned send_cmd responses
through the REAL run_item code path via mock sessions -- the mock only
replaces serial IO, never judgment logic.
"""

import json
from pathlib import Path

from .orchestrator import run_item


class MockSession:
    """Replays queued (text, ok) responses for one target."""

    def __init__(self, target, prompt, queue):
        self.target = target
        self.prompt = prompt
        self._q = queue

    def send_cmd(self, cmd, timeout_s=10):
        if not self._q:
            raise ValueError("selftest case ran out of canned responses at "
                             "%s> %s" % (self.target, cmd or "<CR>"))
        r = self._q.pop(0)
        return r.get("text", ""), bool(r.get("ok", True))


class MockSessions(dict):
    """Dict of targets sharing one response queue (step order)."""

    def __init__(self, responses, targets):
        super().__init__()
        queue = list(responses)
        for name, t in targets.items():
            self[name] = MockSession(name, t["prompt"], queue)


def _load_case_files(cases_dir):
    if not cases_dir.is_dir():
        raise ValueError("selftest_cases dir not found: %s" % cases_dir)
    cases = []
    for jf in sorted(cases_dir.glob("*.json")):
        if jf.name.startswith("_") or jf.name == "extract_from_logs.py":
            continue
        try:
            with open(jf, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError("%s: cannot load: %s" % (jf.name, e))
        if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
            raise ValueError("%s: expected {\"cases\": [...]}" % jf.name)
        for c in data["cases"]:
            for key in ("name", "item", "responses", "expect_pass"):
                if key not in c:
                    raise ValueError("%s: case missing key %r" % (jf.name, key))
            if not isinstance(c["item"], int) or isinstance(c["item"], bool):
                raise ValueError("%s: case %r item must be an int"
                                 % (jf.name, c["name"]))
            if not isinstance(c["responses"], list):
                raise ValueError("%s: case %r responses must be a list"
                                 % (jf.name, c["name"]))
            c["_source"] = jf.name
            cases.append(c)
    if not cases:
        raise ValueError("no selftest cases in %s" % cases_dir)
    return cases


def run_selftest(proj_dir, load_project, load_verify_items, load_judges,
                 resolve_judges):
    """Returns process exit code: 0 = all PASS, 1 = failures."""
    failures = []
    total = [0]

    def check(name, cond):
        total[0] += 1
        print("[%s] %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            failures.append(name)

    proj = None
    try:
        proj = load_project(proj_dir)
        check("project config valid (%s)" % proj_dir, True)
    except ValueError as e:
        check("project config valid (%s)" % proj_dir, False)
        print("        %s" % e)

    items = None
    try:
        items = load_verify_items(proj_dir)
        check("verify items discovered: %d (ids: %s)"
              % (len(items), ", ".join(str(i["id"]) for i in items)), True)
    except ValueError as e:
        check("verify items discovered", False)
        print("        %s" % e)

    judges = None
    try:
        judges_mod = load_judges(proj_dir)
        judges = resolve_judges(judges_mod, items or [])
        check("judges.py loadable + judge.fn resolved", True)
    except ValueError as e:
        check("judges.py loadable + judge.fn resolved", False)
        print("        %s" % e)

    if proj is None or items is None or judges is None:
        print("selftest: %d cases, %d failed" % (total[0], len(failures)))
        return 1

    try:
        cases = _load_case_files(Path(proj_dir) / "selftest_cases")
    except ValueError as e:
        check("selftest cases loadable", False)
        print("        %s" % e)
        print("selftest: %d cases, %d failed" % (total[0], len(failures)))
        return 1

    by_id = {it["id"]: it for it in items}
    targets = {t["name"]: {"prompt": t["prompt"]} for t in proj["targets"]}
    noop_sleep = lambda seconds: None

    for case in cases:
        item = by_id.get(case["item"])
        if item is None:
            check("%s: unknown item id %r" % (case["name"], case["item"]),
                  False)
            continue
        sessions = MockSessions(case["responses"], targets)
        try:
            res = run_item(item, sessions, noop_sleep, judges)
            got_pass = res.passed
        except Exception as e:
            check("%s: replay error (%s)" % (case["name"], e), False)
            continue
        ok = got_pass == bool(case["expect_pass"])
        check("%s: %s" % (case["name"],
                          "expect PASS" if case["expect_pass"] else "expect FAIL"),
              ok)
        on_fail_ok = True
        if "expect_on_fail" in case:
            fired = any(c.kind == "on_fail" for c in res.checks)
            on_fail_ok = fired == bool(case["expect_on_fail"])
            check("%s: on_fail %s"
                  % (case["name"], "fired" if fired else "not fired"),
                  on_fail_ok)
        if not ok or not on_fail_ok:
            for c in res.checks:
                tag = "" if c.kind == "step" else "[%s] " % c.kind
                print("        %scheck %d: %s -> %s %s"
                      % (tag, c.index, c.desc,
                         "PASS" if c.passed else "FAIL", c.detail))

    print("selftest: %d cases, %d failed" % (total[0], len(failures)))
    return 0 if not failures else 1
