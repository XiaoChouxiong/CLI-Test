# -*- coding: utf-8 -*-
"""Project judge functions for the _template demo project.

Every judge follows the framework contract:
    fn(text, args, ctx) -> (ok, detail, evidence)
  - text: this step's command echo, ANSI already stripped by the framework
  - args: the step's judge.args dict from verify_items.json
  - ctx:  {"target": ..., "prompt": ...} injected by the framework

Return values:
  - ok:       True when the step passes
  - detail:   one-line human readable verdict (goes into the report)
  - evidence: list of echo lines backing the verdict (may be empty)

These three judges are intentionally small and generic. Real projects keep
the same contract but implement whatever pass criteria they need -- see the
repo README for the full contract description.
"""

import re

# Demo match: "fw version: v2.3.1" -> captures "2.3.1".
# Override per step via judge.args.pattern when your device differs.
VERSION_RE = re.compile(r"\bversion[:\s]+v?([\w.\-]+)", re.IGNORECASE)


def prompt_seen(text, args, ctx):
    ok = ctx["prompt"] in text
    return ok, ("prompt seen" if ok else "prompt NOT seen"), []


def not_contains(text, args, ctx):
    needles = args.get("any", [])
    hit = [s for s in needles if s in text]
    if not hit:
        return True, "no forbidden string found", []
    evidence = [ln for ln in text.splitlines() if any(s in ln for s in hit)]
    return False, "forbidden string(s): %s" % "; ".join(hit), evidence


def extract_version(text, args, ctx):
    pattern = re.compile(args["pattern"]) if args.get("pattern") else VERSION_RE
    m = pattern.search(text)
    if not m:
        return False, "version not found by pattern", []
    evidence = [ln for ln in text.splitlines() if pattern.search(ln)]
    return True, "version: %s" % m.group(1), evidence
