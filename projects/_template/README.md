# Project template

Copy this directory to `projects/<your-project>/` and edit three files --
the framework (`verifyfw/`) never changes when a project is added.

## Files to edit

| File | What it defines |
|---|---|
| `project.json` | Environment: serial targets (name + shell prompt) and serial line settings. COM ports are given on the command line, not stored here. |
| `verify_items.json` | Verification flow: an ordered list of items, each a linear sequence of steps (`target` + `cmd` + `timeout_s`, or `type: "sleep"`), optionally with a `judge` per step. |
| `judges.py` | Pass criteria: plain Python functions following the contract below. |

Plus `selftest_cases/*.json`: canned echo samples replayed offline by
`python main.py selftest <projdir>` so judges can be tested without hardware.

## Judge contract

```python
def my_judge(text, args, ctx):
    """Return (ok, detail, evidence)."""
```

- `text` -- the step's command echo, ANSI escape codes already stripped
- `args` -- the `judge.args` object from `verify_items.json` (may be empty)
- `ctx` -- `{"target": "<target name>", "prompt": "<its prompt>"}`
- return `ok` (bool), `detail` (one-line verdict for the report),
  `evidence` (list of echo lines backing the verdict)

Steps without a `judge` only fail on prompt timeout; steps with one are
judged after the framework layer confirms the prompt returned.

## Try it offline first

```bash
python main.py selftest projects/_template/
```

## Then run against real hardware

```bash
python main.py run projects/_template/ --target dut0=COM3 --target dut1=COM4
```

## What the framework does not judge

Stateless single-echo checks are what `verify_items.json` + `judges.py` are
for. Scenarios that need cross-step state, cross-target correlation or
timing assertions should be expressed inside a judge function in Python --
the framework deliberately keeps the configuration language stateless.
