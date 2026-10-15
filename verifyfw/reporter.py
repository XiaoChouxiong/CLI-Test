# -*- coding: utf-8 -*-
"""Reporter: console output plus result.json / result.txt under logs/run_*.

Item results carry a `checks` list, one per executed step (command steps
and sleeps alike), each with pass/fail, detail and evidence lines.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CheckOutcome:
    index: int
    desc: str
    passed: bool
    detail: str = ""
    evidence: list = field(default_factory=list)


@dataclass
class ItemResult:
    item_id: int
    name: str
    passed: bool
    duration_s: float
    checks: list = field(default_factory=list)


@dataclass
class RoundResult:
    round_no: int
    passed: bool
    items: list = field(default_factory=list)
    duration_s: float = 0.0


class Reporter:
    """Console output plus result.json / result.txt under logs/run_*."""

    def __init__(self, run_dir, mode, project):
        self.run_dir = run_dir
        self.json_path = run_dir / "result.json"
        self.txt_path = run_dir / "result.txt"
        self.meta = {
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": mode,
            "project": project,
            "rounds": [],
        }
        run_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _item_lines(item, show_evidence):
        lines = ["  [%s] #%d %s (%.1fs)"
                 % ("PASS" if item.passed else "FAIL", item.item_id,
                    item.name, item.duration_s)]
        for ck in item.checks:
            lines.append("    check %d: %s -> %s %s"
                         % (ck.index, ck.desc,
                            "PASS" if ck.passed else "FAIL", ck.detail))
            # Console stays readable: full evidence only for failures / files
            if show_evidence or not ck.passed:
                for ev in ck.evidence:
                    lines.append("      | %s" % ev.strip())
        return lines

    def round(self, rr):
        self.meta["rounds"].append(rr)
        print("[%s] === Round %d %s (%.1fs) ==="
              % (datetime.now().strftime("%H:%M:%S"), rr.round_no,
                 "PASS" if rr.passed else "FAIL", rr.duration_s))
        for item in rr.items:
            for ln in self._item_lines(item, show_evidence=False):
                print(ln)
        self._flush()

    def _flush(self):
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2,
                      default=lambda o: o.__dict__)
        with open(self.txt_path, "w", encoding="utf-8") as f:
            for rr in self.meta["rounds"]:
                f.write("=== Round %d %s ===\n"
                        % (rr.round_no, "PASS" if rr.passed else "FAIL"))
                for item in rr.items:
                    for ln in self._item_lines(item, show_evidence=True):
                        f.write(ln + "\n")
