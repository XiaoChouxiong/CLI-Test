# -*- coding: utf-8 -*-
"""Serial session: one port bound to one target, with a raw log.

Two framework-level properties:
  - the prompt comes from the project targets config (any number of targets)
  - D7: the raw log is zero-processing -- raw bytes straight to disk, no
    timestamps injected, no decode step; decoding happens in memory only
    for prompt detection and judging.
"""

import time

try:
    import serial
except ImportError:  # pragma: no cover - env guard mirrors old script
    serial = None

QUIET_S = 0.5   # silence window confirming the shell prompt is the final one
POLL_S = 0.02   # serial read poll interval


def serial_available():
    return serial is not None


class SerialSession:
    """One serial port bound to one named target (prompt from config)."""

    def __init__(self, target, prompt, port, serial_cfg, log_path):
        self.target = target
        self.prompt = prompt
        self.port = port
        self.cfg = serial_cfg
        self.ser = None
        # D7: binary, unbuffered -- the log keeps the exact byte stream so it
        # stays diffable and replayable by any tool.
        self.log_f = open(log_path, "wb", buffering=0)

    def open(self):
        parity = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                  "O": serial.PARITY_ODD}[str(self.cfg.get("parity", "N"))]
        self.ser = serial.Serial(
            port=self.port,
            baudrate=int(self.cfg.get("baudrate", 115200)),
            bytesize=int(self.cfg.get("bytesize", 8)),
            parity=parity,
            stopbits=int(self.cfg.get("stopbits", 1)),
            timeout=POLL_S,
        )

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.log_f.close()

    def _read_chunk(self):
        """Non-blocking read; raw bytes go to the log untouched (D7)."""
        n = self.ser.in_waiting
        if n <= 0:
            return ""
        data = self.ser.read(n)
        self.log_f.write(data)
        return data.decode("utf-8", errors="replace")

    def drain(self):
        """Read away pending bytes (e.g. boot banner) into the log only."""
        while True:
            chunk = self._read_chunk()
            if not chunk:
                return

    def send_cmd(self, cmd, timeout_s):
        """Send cmd + CRLF, capture echo until the prompt re-appears at the
        end of output plus a quiet window, or timeout.

        Returns (captured_text, prompt_seen).
        """
        self.drain()
        self.ser.write((cmd + "\r\n").encode("utf-8"))
        captured = ""
        last_data = time.monotonic()
        deadline = last_data + timeout_s
        while time.monotonic() < deadline:
            chunk = self._read_chunk()
            if chunk:
                captured += chunk
                last_data = time.monotonic()
            if (captured.rstrip().endswith(self.prompt)
                    and time.monotonic() - last_data >= QUIET_S):
                return captured, True
            time.sleep(POLL_S)
        return captured, False

    def read_for(self, seconds):
        """Read and log for a duration, return captured text (sleep steps,
        stability wait), so link output during the wait is never lost."""
        captured = ""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            captured += self._read_chunk()
            time.sleep(POLL_S)
        return captured


def read_for_all(sessions, seconds):
    """Keep all ports reading/logging while wall time passes."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for s in sessions.values():
            s._read_chunk()
        time.sleep(POLL_S)
