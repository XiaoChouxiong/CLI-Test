# CLI-Test

A small, dependency-light framework for **serial-port verification**:
drive your device's shell over UART, run configured verification items,
judge each command's echo with project-defined Python functions, and get
structured reports plus exit codes that plug straight into CI.

- **Config-driven flow** -- verification items, commands and waits live in
  a JSON file (`verify_items.json`), easy to read, diff and review.
- **Pass criteria in Python** -- each judged step calls a function in the
  project's `judges.py` (`fn(text, args, ctx) -> (ok, detail, evidence)`),
  so the expressiveness of real code is available where plain config ends.
- **New project = copy a directory** -- a project is three files plus
  offline test samples; the framework itself never changes.
- **Offline self-test** -- canned echo samples are replayed through the
  real execution path, so judges and configuration can be validated
  without hardware.
- **Single dependency** -- [pyserial](https://pypi.org/project/pyserial/)
  only; everything else is the standard library (Python 3.8+).

## Quick start

```bash
pip install pyserial

# Offline: replay the bundled template project (no hardware needed)
python main.py selftest projects/_template/

# Real hardware: bind each target to its COM port
python main.py run projects/_template/ --target dut0=COM3 --target dut1=COM4
```

## Writing a project

Copy `projects/_template/` to `projects/<your-project>/` and edit:

| File | Defines |
|---|---|
| `project.json` | Environment: serial targets (name + shell prompt) and line settings. COM ports are given on the command line, never stored here. |
| `verify_items.json` | Flow: ordered verification items, each a linear list of steps. |
| `judges.py` | Pass criteria: judge functions. |
| `selftest_cases/*.json` | Canned echo samples for offline replay. |

A step is either a command (`target`, `cmd`, `timeout_s`, optional
`judge`) or a wait (`type: "sleep"`, `seconds`). During a wait the serial
ports keep recording -- nothing is dropped.

```json
{"target": "dut0", "cmd": "status", "timeout_s": 10,
 "judge": {"fn": "not_contains", "args": {"any": ["error", "fault"]}}}
```

### Exception handling (`on_fail`)

An item may declare an optional `on_fail` list of steps (same schema as
`steps`, `sleep` included). They run **only when the item fails** -- a
prompt timeout or a judge mismatch -- best-effort and in declared order,
before the framework returns the FAIL result, e.g. to capture a diagnostic
dump for post-mortem:

```json
{"id": 2, "name": "status check",
 "steps": [{"target": "dut0", "cmd": "status", "timeout_s": 10}],
 "on_fail": [{"target": "dut0", "cmd": "dump", "timeout_s": 30}]}
```

Their own outcome never changes the item verdict or the exit code: each hook
step is recorded as an `[on_fail]` check (with its own prompt-timeout
verdict) and its echo still lands in the target's raw log. Offline selftest
cases can assert whether the hook ran with `"expect_on_fail": true|false`.

### Judge contract

```python
def not_contains(text, args, ctx):
    """Return (ok, detail, evidence)."""
    hit = [s for s in args.get("any", []) if s in text]
    ...
```

- `text` -- the step's echo, ANSI escape codes already stripped
- `args` -- the `judge.args` object from `verify_items.json`
- `ctx` -- `{"target": "<name>", "prompt": "<its prompt>"}`
- return `ok` (bool), `detail` (one-line verdict), `evidence` (echo lines)

Every step is also guarded by the framework layer: the command's echo must
end with the target's prompt (silence-confirmed), otherwise the step fails
with `timeout, prompt not seen`. Judges only ever see echoes that passed
that layer. Steps without a `judge` rely on this layer alone.

## CLI reference

```
python main.py run <projdir> --target NAME=COM [--target ...]
                     [--mode {0,1}] [--max-rounds N]
                     [--continue-on-fail] [--no-judge]
python main.py selftest <projdir>
```

| Option | Meaning |
|---|---|
| `--target NAME=COM` | Bind target NAME (from `project.json`) to a serial port. One per target. |
| `--mode 0` | Default. Single round: stop at the first failure and keep the failure scene on the device. |
| `--mode 1` | Loop rounds. On failure stop entirely by default; see `--continue-on-fail`. |
| `--max-rounds N` | Mode 1 only: stop after N rounds and print statistics (0 = loop until Ctrl+C). |
| `--continue-on-fail` | Mode 1 only: start a reset round after a failed round instead of stopping (soak-test / statistics opt-in). |
| `--no-judge` | Bring-up mode: ignore all judge rules; steps only fail on prompt timeout. |
| exit code | `0` all PASS; `1` FAIL found; `2` usage / config / serial environment error. |

When the project directory is omitted, the bundled project
(`projects/_template/`) is used.

## Logs and reports

Each run writes to `logs/run_<timestamp>/`:

```
logs/run_20260101_120000/
├── dut0.log / dut1.log   # raw byte streams, zero processing (diffable evidence)
├── result.json           # per-step verdicts, details and evidence (machine readable)
└── result.txt            # human readable summary
```

Raw logs are written exactly as received -- no timestamps injected, no
decoding -- so they can be diffed, archived or replayed by any tool.

## Packaging a dedicated exe (optional)

The framework can be frozen with PyInstaller into a single exe with a
project bundled inside; `run` then becomes the default subcommand:

```bash
python -m PyInstaller --onefile --name my_verify \
    --add-data "projects/my_project;projects/my_project" main.py
```

Set `BUNDLED_PROJECT` in `verifyfw/cli.py` to your project name first --
it decides which bundled project is used when no path is given.

## License

Apache-2.0 -- see [LICENSE](LICENSE).

### Third-party notices

None currently. (Portions of a future judge-helper library may be derived
from [openhtf](https://github.com/google/openhtf), Apache-2.0; this
section will carry the required attribution when that lands.)
