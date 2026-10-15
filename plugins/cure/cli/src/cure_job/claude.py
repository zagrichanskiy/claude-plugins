"""The ``claude`` binary seam.

``ClaudeCli`` is the only code that runs the binary. Everything else depends on
the :class:`Claude` protocol, so a test passes a fake.
"""
from __future__ import annotations

import enum
import json
import os
import shlex
import subprocess
from typing import Protocol, Sequence

from .errors import ClaudeError, ClaudeOutcomeUnknown


class SessionStatus(enum.Enum):
    BUSY = "busy"
    IDLE = "idle"
    STOPPED = "stopped"


#: The key and value `claude agents --json` puts on a live session that waits
#: for input. A live entry with any other value, or none, is busy.
IDLE_MARK = ("status", "idle")

#: A name listed more than once takes its strongest entry.
_STRENGTH = {SessionStatus.BUSY: 2, SessionStatus.IDLE: 1, SessionStatus.STOPPED: 0}


class Claude(Protocol):
    def sessions(self) -> dict[str, SessionStatus]:
        """Session name to status, for every session the binary lists."""

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        """Start one background session. Returns when the binary has returned."""


class ClaudeCli:
    TIMEOUT_SECONDS = 60

    def __init__(self, binary: str):
        self.binary = binary

    def sessions(self) -> dict[str, SessionStatus]:
        argv = [self.binary, "agents", "--json", "--all"]
        stdout = self._run(argv)
        try:
            entries = json.loads(stdout)
        except ValueError:
            entries = None
        if not isinstance(entries, list):
            raise ClaudeError(f"{shlex.join(argv)}: the output is not a JSON array")
        found: dict[str, SessionStatus] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            status = _status(entry)
            known = found.get(entry["name"])
            if known is None or _STRENGTH[status] > _STRENGTH[known]:
                found[entry["name"]] = status
        return found

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        argv = [self.binary, "--bg", "--name", name, *extra_args, prompt]
        # Checked here: subprocess reports a missing cwd and a missing binary
        # with the same FileNotFoundError.
        if not os.path.isdir(cwd):
            raise ClaudeError(f"{shlex.join(argv)}: {cwd} is not a directory")
        self._run(argv, cwd=cwd)

    def _run(self, argv: list[str], cwd: str | None = None) -> str:
        command = shlex.join(argv)
        try:
            done = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, errors="replace", timeout=self.TIMEOUT_SECONDS)
        except OSError as e:
            raise ClaudeError(f"{command}: cannot run: {e.strerror or e}") from e
        except subprocess.TimeoutExpired as e:
            raise ClaudeOutcomeUnknown(f"{command}: no exit within {self.TIMEOUT_SECONDS} seconds") from e
        if done.returncode != 0:
            raise ClaudeError(f"{command}: exit {done.returncode}{_first_line(done.stderr)}")
        return done.stdout


def _status(entry: dict) -> SessionStatus:
    # A stopped session stays listed under --all, without a pid.
    if "pid" not in entry:
        return SessionStatus.STOPPED
    key, value = IDLE_MARK
    return SessionStatus.IDLE if entry.get(key) == value else SessionStatus.BUSY


def _first_line(stderr: str) -> str:
    lines = stderr.strip().splitlines()
    return f": {lines[0]}" if lines else ""
